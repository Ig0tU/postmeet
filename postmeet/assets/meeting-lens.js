(function (window, document) {
  "use strict";

  if (window.PatchesXsMeetingLens && typeof window.PatchesXsMeetingLens.register === "function") {
    return;
  }

  var instances = Object.create(null);
  var keyOwners = Object.create(null);
  var observer = null;
  var remotePlayers = [];

  function emit(instance, name, detail, cancelable) {
    var event = new CustomEvent("xs-meeting-lens:" + name, {
      bubbles: true,
      cancelable: Boolean(cancelable),
      detail: Object.assign({
        id: instance.config.id,
        key: instance.config.key
      }, detail || {})
    });
    instance.root.dispatchEvent(event);
    return !event.defaultPrevented;
  }

  function announce(instance, message) {
    var region = instance.root.querySelector("[data-xs-ml-live]");
    if (!region) {
      return;
    }
    region.textContent = "";
    window.setTimeout(function () {
      region.textContent = message;
    }, 20);
  }

  function findRoot(id) {
    var roots = document.querySelectorAll("[data-xs-ml-root]");
    for (var index = 0; index < roots.length; index += 1) {
      if (roots[index].getAttribute("data-xs-ml-root") === id) {
        return roots[index];
      }
    }
    return null;
  }

  function storageFor(mode) {
    try {
      return mode === "local" ? window.localStorage : (mode === "session" ? window.sessionStorage : null);
    } catch (error) {
      return null;
    }
  }

  function readPosition(instance) {
    var storage = storageFor(instance.config.rememberPosition);
    if (!storage) {
      return null;
    }
    try {
      var value = JSON.parse(storage.getItem(instance.config.storageKey));
      if (
        !value
        || value.fingerprint !== instance.config.fingerprint
        || !Number.isFinite(value.time)
        || value.time < 0
        || Date.now() - value.savedAt > 30 * 24 * 60 * 60 * 1000
      ) {
        return null;
      }
      return value.time;
    } catch (error) {
      return null;
    }
  }

  function savePosition(instance, seconds) {
    var storage = storageFor(instance.config.rememberPosition);
    if (!storage || !Number.isFinite(seconds) || seconds < 0) {
      return;
    }
    try {
      storage.setItem(instance.config.storageKey, JSON.stringify({
        fingerprint: instance.config.fingerprint,
        time: Math.floor(seconds),
        savedAt: Date.now()
      }));
    } catch (error) {
      emit(instance, "error", { code: "storage", error: error });
    }
  }

  function BaseProvider(instance) {
    this.instance = instance;
    this.readyState = false;
    this.mounted = false;
    this.currentTime = 0;
  }
  BaseProvider.prototype.mount = function () {
    this.mounted = true;
    this.readyState = true;
    this.instance.providerReady();
    return true;
  };
  BaseProvider.prototype.destroy = function () {};
  BaseProvider.prototype.ready = function () {
    return this.readyState;
  };
  BaseProvider.prototype.seek = function () {
    return false;
  };
  BaseProvider.prototype.getTime = function () {
    return this.currentTime;
  };
  BaseProvider.prototype.play = function () {
    return false;
  };
  BaseProvider.prototype.pause = function () {
    return false;
  };

  function NativeProvider(instance) {
    BaseProvider.call(this, instance);
    this.video = null;
    this.listeners = [];
  }
  NativeProvider.prototype = Object.create(BaseProvider.prototype);
  NativeProvider.prototype.constructor = NativeProvider;
  NativeProvider.prototype.mount = function () {
    if (this.mounted) {
      return true;
    }
    this.video = this.instance.root.querySelector("[data-xs-ml-player] video");
    if (!this.video) {
      return false;
    }
    this.mounted = true;
    var provider = this;
    ["loadedmetadata", "canplay"].forEach(function (name) {
      var ready = function () {
        if (!provider.readyState) {
          provider.readyState = true;
          provider.instance.providerReady();
        }
      };
      provider.video.addEventListener(name, ready);
      provider.listeners.push([name, ready]);
    });
    ["timeupdate", "seeking"].forEach(function (name) {
      var update = function () {
        provider.currentTime = provider.video.currentTime || 0;
        provider.instance.onTime(provider.currentTime);
      };
      provider.video.addEventListener(name, update);
      provider.listeners.push([name, update]);
    });
    ["play", "pause", "ended"].forEach(function (name) {
      var relay = function () {
        emit(provider.instance, name, { time: provider.video.currentTime || 0 });
      };
      provider.video.addEventListener(name, relay);
      provider.listeners.push([name, relay]);
    });
    if (this.video.readyState >= 1) {
      this.readyState = true;
      this.instance.providerReady();
    }
    return true;
  };
  NativeProvider.prototype.seek = function (seconds) {
    if (!this.video || !Number.isFinite(seconds)) {
      return false;
    }
    try {
      this.video.currentTime = seconds;
      this.currentTime = seconds;
      return true;
    } catch (error) {
      return false;
    }
  };
  NativeProvider.prototype.getTime = function () {
    return this.video ? this.video.currentTime || 0 : 0;
  };
  NativeProvider.prototype.play = function () {
    if (!this.video) {
      return false;
    }
    var promise = this.video.play();
    if (promise && typeof promise.catch === "function") {
      promise.catch(function () {});
    }
    return true;
  };
  NativeProvider.prototype.pause = function () {
    if (!this.video) {
      return false;
    }
    this.video.pause();
    return true;
  };
  NativeProvider.prototype.destroy = function () {
    var provider = this;
    this.listeners.forEach(function (entry) {
      provider.video.removeEventListener(entry[0], entry[1]);
    });
    this.listeners = [];
  };

  function RemoteProvider(instance, kind) {
    BaseProvider.call(this, instance);
    this.kind = kind;
    this.frame = null;
    this.poller = null;
    this.origin = "";
  }
  RemoteProvider.prototype = Object.create(BaseProvider.prototype);
  RemoteProvider.prototype.constructor = RemoteProvider;
  RemoteProvider.prototype.mount = function () {
    if (this.mounted) {
      return true;
    }
    var host = this.instance.root.querySelector("[data-xs-ml-player]");
    var url = this.instance.config.media.embedUrl;
    if (!host || !url || host.querySelector("iframe")) {
      return false;
    }
    this.mounted = true;
    try {
      this.origin = new URL(url, document.baseURI).origin;
    } catch (error) {
      return false;
    }
    this.frame = document.createElement("iframe");
    this.frame.src = url;
    this.frame.title = host.getAttribute("data-player-title") || "Meeting recording";
    this.frame.allow = "autoplay; fullscreen; picture-in-picture";
    this.frame.setAttribute("allowfullscreen", "");
    this.frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    host.replaceChildren(this.frame);
    remotePlayers.push(this);
    var provider = this;
    this.frame.addEventListener("load", function () {
      provider.readyState = true;
      if (provider.kind === "youtube") {
        provider.post({ event: "listening", id: provider.instance.config.id });
        provider.command("addEventListener", ["onStateChange"]);
        provider.poller = window.setInterval(function () {
          provider.command("getCurrentTime", []);
        }, 500);
      } else if (provider.kind === "vimeo") {
        ["timeupdate", "play", "pause", "ended", "loaded"].forEach(function (event) {
          provider.post({ method: "addEventListener", value: event });
        });
      }
      provider.instance.providerReady();
    });
    return true;
  };
  RemoteProvider.prototype.post = function (message) {
    if (this.frame && this.frame.contentWindow && this.origin) {
      this.frame.contentWindow.postMessage(JSON.stringify(message), this.origin);
    }
  };
  RemoteProvider.prototype.command = function (name, args) {
    this.post({ event: "command", func: name, args: args || [] });
  };
  RemoteProvider.prototype.seek = function (seconds) {
    if (!this.frame || !Number.isFinite(seconds) || this.kind === "iframe") {
      return false;
    }
    this.currentTime = seconds;
    if (this.kind === "youtube") {
      this.command("seekTo", [seconds, true]);
    } else {
      this.post({ method: "setCurrentTime", value: seconds });
    }
    return true;
  };
  RemoteProvider.prototype.play = function () {
    if (this.kind === "youtube") {
      this.command("playVideo", []);
      return true;
    }
    if (this.kind === "vimeo") {
      this.post({ method: "play" });
      return true;
    }
    return false;
  };
  RemoteProvider.prototype.pause = function () {
    if (this.kind === "youtube") {
      this.command("pauseVideo", []);
      return true;
    }
    if (this.kind === "vimeo") {
      this.post({ method: "pause" });
      return true;
    }
    return false;
  };
  RemoteProvider.prototype.receive = function (data) {
    if (!data || typeof data !== "object") {
      return;
    }
    if (this.kind === "youtube") {
      var info = data.info || {};
      if (Number.isFinite(info.currentTime)) {
        this.currentTime = info.currentTime;
        this.instance.onTime(this.currentTime);
      }
      if (Number.isFinite(info.playerState)) {
        var eventName = info.playerState === 1 ? "play" : (info.playerState === 2 ? "pause" : (info.playerState === 0 ? "ended" : ""));
        if (eventName) {
          emit(this.instance, eventName, { time: this.currentTime });
        }
      }
    } else if (this.kind === "vimeo") {
      if (data.event === "timeupdate" && data.data && Number.isFinite(data.data.seconds)) {
        this.currentTime = data.data.seconds;
        this.instance.onTime(this.currentTime);
      }
      if (["play", "pause", "ended"].indexOf(data.event) !== -1) {
        emit(this.instance, data.event, { time: this.currentTime });
      }
      if (data.method === "getCurrentTime" && Number.isFinite(data.value)) {
        this.currentTime = data.value;
        this.instance.onTime(this.currentTime);
      }
    }
  };
  RemoteProvider.prototype.destroy = function () {
    if (this.poller) {
      window.clearInterval(this.poller);
    }
    var index = remotePlayers.indexOf(this);
    if (index !== -1) {
      remotePlayers.splice(index, 1);
    }
    if (this.frame) {
      this.frame.src = "about:blank";
      this.frame.remove();
    }
  };

  function LinkProvider(instance) {
    BaseProvider.call(this, instance);
  }
  LinkProvider.prototype = Object.create(BaseProvider.prototype);
  LinkProvider.prototype.constructor = LinkProvider;

  function createProvider(instance) {
    var type = instance.config.media.provider;
    if (type === "native") {
      return new NativeProvider(instance);
    }
    if (type === "youtube" || type === "vimeo" || type === "iframe") {
      return new RemoteProvider(instance, type);
    }
    return new LinkProvider(instance);
  }

  function normalize(value) {
    return String(value || "").trim().toLocaleLowerCase();
  }

  function filter(instance, source) {
    var query = normalize(instance.search ? instance.search.value : "");
    var type = instance.typeFilter ? instance.typeFilter.value : "";
    var status = instance.statusFilter ? instance.statusFilter.value : "";
    var records = Array.prototype.slice.call(instance.root.querySelectorAll("[data-xs-ml-record]"));
    var visible = 0;

    instance.root.querySelectorAll("details[data-xs-ml-filter-open]").forEach(function (details) {
      details.open = false;
      details.removeAttribute("data-xs-ml-filter-open");
    });
    records.forEach(function (record) {
      var matches = (!query || normalize(record.getAttribute("data-xs-ml-search")).indexOf(query) !== -1)
        && (!type || record.getAttribute("data-xs-ml-type") === type)
        && (!status || record.getAttribute("data-xs-ml-status") === status);
      record.classList.toggle("xs-ml-filtered", !matches);
      if (matches) {
        visible += 1;
        var details = record.closest("details");
        while (details && instance.root.contains(details)) {
          if (!details.open) {
            details.open = true;
            details.setAttribute("data-xs-ml-filter-open", "true");
          }
          details = details.parentElement ? details.parentElement.closest("details") : null;
        }
        var agendaKey = record.getAttribute("data-xs-ml-agenda");
        if (agendaKey) {
          records.forEach(function (candidate) {
            if (
              candidate.getAttribute("data-xs-ml-type") === "agenda"
              && candidate.getAttribute("data-xs-ml-key") === agendaKey
            ) {
              candidate.classList.remove("xs-ml-filtered");
            }
          });
        }
        var parent = record.parentElement ? record.parentElement.closest("[data-xs-ml-record]") : null;
        while (parent) {
          parent.classList.remove("xs-ml-filtered");
          parent = parent.parentElement ? parent.parentElement.closest("[data-xs-ml-record]") : null;
        }
      }
    });

    if (instance.results) {
      instance.results.textContent = query || type || status
        ? visible + " matching record" + (visible === 1 ? "" : "s") + "."
        : records.length + " meeting records.";
    }
    emit(instance, query ? "search" : "filter", {
      query: query,
      type: type,
      status: status,
      count: visible,
      source: source || "user"
    });
    if (window.UIkit && typeof window.UIkit.update === "function") {
      window.UIkit.update(instance.root);
    }
    return visible;
  }

  function clearFilters(instance) {
    if (instance.search) {
      instance.search.value = "";
    }
    if (instance.typeFilter) {
      instance.typeFilter.value = "";
    }
    if (instance.statusFilter) {
      instance.statusFilter.value = "";
    }
    return filter(instance, "reset");
  }

  function setCurrent(instance, kind, key, options) {
    options = options || {};
    if (!key || !emit(instance, "beforechange", { kind: kind, recordKey: key, source: options.source || "api" }, true)) {
      return false;
    }
    var selector = kind === "chapter" ? "[data-xs-ml-type='chapter']" : "[data-xs-ml-type='agenda']";
    var target = null;
    instance.root.querySelectorAll(selector).forEach(function (record) {
      var active = record.getAttribute("data-xs-ml-key") === key;
      record.setAttribute("aria-current", active ? "true" : "false");
      if (active) {
        target = record;
      }
    });
    if (!target) {
      return false;
    }
    var details = target.closest("details");
    while (details && instance.root.contains(details)) {
      details.open = true;
      details = details.parentElement ? details.parentElement.closest("details") : null;
    }
    if (kind === "chapter") {
      instance.state.chapter = key;
      var agendaKey = target.getAttribute("data-xs-ml-agenda");
      if (agendaKey) {
        setCurrent(instance, "agenda", agendaKey, { source: options.source, url: false, announce: false });
      }
    } else {
      instance.state.agenda = key;
    }
    if (options.scroll && target.scrollIntoView) {
      target.scrollIntoView({ behavior: instance.reducedMotion ? "auto" : "smooth", block: "nearest" });
    }
    if (options.url !== false) {
      writeUrl(instance, kind, key, options.replace);
    }
    if (options.announce !== false) {
      var title = target.querySelector(".xs-ml-agenda-title,.xs-ml-chapter-title");
      announce(instance, (kind === "chapter" ? "Selected chapter " : "Selected agenda item ") + (title ? title.textContent : key) + ".");
    }
    emit(instance, kind, { recordKey: key, source: options.source || "api" });
    emit(instance, "change", { kind: kind, recordKey: key, source: options.source || "api" });
    return true;
  }

  function seek(instance, seconds, options) {
    options = options || {};
    seconds = Number(seconds);
    if (!Number.isFinite(seconds) || seconds < 0 || !emit(instance, "beforeseek", {
      seconds: seconds,
      chapterKey: options.chapterKey || "",
      source: options.source || "api"
    }, true)) {
      return false;
    }
    if (!instance.config.media.seekable) {
      return false;
    }
    if (!instance.provider.ready()) {
      instance.pendingSeek = { seconds: seconds, options: options };
      if (!loadPlayer(instance)) {
        instance.pendingSeek = null;
        return false;
      }
    } else {
      if (!instance.provider.seek(seconds)) {
        return false;
      }
      if (options.play) {
        instance.provider.play();
      }
    }
    if (options.chapterKey) {
      setCurrent(instance, "chapter", options.chapterKey, {
        source: options.source,
        url: options.url,
        scroll: false
      });
    }
    announce(instance, "Recording position set to " + formatTime(seconds) + ".");
    emit(instance, "seek", { seconds: seconds, chapterKey: options.chapterKey || "", source: options.source || "api" });
    return true;
  }

  function formatTime(seconds) {
    var total = Math.max(0, Math.floor(seconds));
    var hours = Math.floor(total / 3600);
    var minutes = Math.floor((total % 3600) / 60);
    var remainder = total % 60;
    return hours
      ? hours + ":" + String(minutes).padStart(2, "0") + ":" + String(remainder).padStart(2, "0")
      : minutes + ":" + String(remainder).padStart(2, "0");
  }

  function activeChapter(instance, seconds) {
    var found = null;
    instance.config.chapters.forEach(function (chapter) {
      var beforeEnd = chapter.end === null || seconds < chapter.end;
      if (seconds >= chapter.start && beforeEnd && (!found || chapter.start >= found.start)) {
        found = chapter;
      }
    });
    return found;
  }

  function onTime(instance, seconds) {
    instance.state.time = seconds;
    if (Date.now() - instance.lastSaved > 5000) {
      savePosition(instance, seconds);
      instance.lastSaved = Date.now();
    }
    if (!instance.config.syncEnabled || !instance.state.follow) {
      return;
    }
    var chapter = activeChapter(instance, seconds);
    if (chapter && chapter.key !== instance.state.chapter) {
      setCurrent(instance, "chapter", chapter.key, {
        source: "playback",
        url: false,
        announce: false,
        scroll: instance.config.scrollActive
      });
    }
  }

  function loadPlayer(instance) {
    if (instance.provider.ready()) {
      return true;
    }
    if (!emit(instance, "beforeplayerload", { provider: instance.config.media.provider }, true)) {
      return false;
    }
    var mounted = instance.provider.mount();
    if (!mounted) {
      emit(instance, "error", { code: "provider-mount", provider: instance.config.media.provider });
    }
    return mounted;
  }

  function providerReady(instance) {
    var remembered = readPosition(instance);
    if (instance.pendingSeek) {
      var pending = instance.pendingSeek;
      instance.pendingSeek = null;
      instance.provider.seek(pending.seconds);
      if (pending.options.play) {
        instance.provider.play();
      }
    } else if (remembered !== null) {
      instance.provider.seek(remembered);
      announce(instance, "Saved recording position restored to " + formatTime(remembered) + ". Playback remains paused.");
    }
    emit(instance, "providerready", { provider: instance.config.media.provider });
  }

  function readUrl(instance) {
    if (instance.config.urlMode === "hash") {
      var prefix = "#meeting-" + instance.config.key + "--";
      if (window.location.hash.indexOf(prefix) === 0) {
        var value = window.location.hash.slice(prefix.length);
        var split = value.indexOf("-");
        if (split > 0) {
          return { kind: value.slice(0, split), key: value.slice(split + 1) };
        }
      }
    } else if (instance.config.urlMode === "query") {
      var query = new URLSearchParams(window.location.search).get(instance.config.urlParameter);
      if (query) {
        var separator = query.indexOf(":");
        if (separator > 0) {
          return { kind: query.slice(0, separator), key: query.slice(separator + 1) };
        }
      }
    }
    return null;
  }

  function writeUrl(instance, kind, key, replace) {
    if (!instance.config.updateUrl || instance.duplicateKey || instance.config.urlMode === "none") {
      return;
    }
    var url = new URL(window.location.href);
    if (instance.config.urlMode === "hash") {
      url.hash = "meeting-" + instance.config.key + "--" + kind + "-" + key;
    } else {
      url.searchParams.set(instance.config.urlParameter, kind + ":" + key);
    }
    window.history[replace ? "replaceState" : "pushState"]({}, "", url.toString());
  }

  function syncUrl(instance) {
    var value = readUrl(instance);
    if (!value || ["agenda", "chapter"].indexOf(value.kind) === -1) {
      return false;
    }
    if (value.kind === "chapter") {
      var chapter = instance.config.chapters.find(function (entry) {
        return entry.key === value.key;
      });
      if (chapter) {
        seek(instance, chapter.start, { chapterKey: chapter.key, source: "url", url: false, play: false });
        return true;
      }
    }
    return setCurrent(instance, "agenda", value.key, { source: "url", url: false, scroll: true });
  }

  function handleClick(instance, event) {
    var button = event.target.closest("[data-xs-ml-load],[data-xs-ml-seek],[data-xs-ml-clear],[data-xs-ml-print],[data-xs-ml-follow],[data-xs-ml-resource-link]");
    if (!button || !instance.root.contains(button)) {
      return;
    }
    if (button.hasAttribute("data-xs-ml-resource-link")) {
      var detail = {
        recordKey: button.getAttribute("data-xs-ml-resource-link"),
        url: button.href
      };
      emit(instance, "resource", detail);
      emit(instance, "documentopen", detail);
    } else if (button.hasAttribute("data-xs-ml-load")) {
      loadPlayer(instance);
    } else if (button.hasAttribute("data-xs-ml-seek")) {
      seek(instance, button.getAttribute("data-xs-ml-seek"), {
        chapterKey: button.getAttribute("data-xs-ml-chapter") || "",
        source: "user",
        play: true,
        url: true
      });
    } else if (button.hasAttribute("data-xs-ml-clear")) {
      clearFilters(instance);
    } else if (button.hasAttribute("data-xs-ml-print")) {
      emit(instance, "print", {});
      window.print();
    } else {
      instance.state.follow = !instance.state.follow;
      button.setAttribute("aria-pressed", instance.state.follow ? "true" : "false");
      var label = button.querySelector("[data-xs-ml-follow-label]");
      if (label) {
        label.textContent = instance.state.follow ? "On" : "Off";
      }
      emit(instance, "change", { kind: "follow", value: instance.state.follow });
    }
  }

  function register(config) {
    if (!config || !config.id || !config.key) {
      return false;
    }
    var root = findRoot(config.id);
    if (!root) {
      return false;
    }
    if (instances[config.id]) {
      destroy(config.id);
    }
    var media = config.media || { provider: "link", valid: false };
    config.media = media;
    var instance = {
      config: config,
      root: root,
      provider: null,
      pendingSeek: null,
      duplicateKey: Boolean(keyOwners[config.key] && keyOwners[config.key] !== config.id),
      reducedMotion: window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      search: root.querySelector("[data-xs-ml-search]"),
      typeFilter: root.querySelector("[data-xs-ml-filter-type]"),
      statusFilter: root.querySelector("[data-xs-ml-filter-status]"),
      results: root.querySelector("[data-xs-ml-results]"),
      lastSaved: 0,
      state: {
        agenda: "",
        chapter: "",
        time: 0,
        follow: Boolean(config.followPlayback),
        loaded: media.provider === "native" || media.provider === "link"
      }
    };
    instance.onTime = function (seconds) {
      onTime(instance, seconds);
    };
    instance.providerReady = function () {
      instance.state.loaded = true;
      providerReady(instance);
    };
    instance.provider = createProvider(instance);
    instances[config.id] = instance;
    if (!keyOwners[config.key]) {
      keyOwners[config.key] = config.id;
    }

    instance.clickHandler = function (event) {
      handleClick(instance, event);
    };
    instance.inputHandler = function () {
      window.clearTimeout(instance.filterTimer);
      instance.filterTimer = window.setTimeout(function () {
        filter(instance, "user");
      }, 120);
    };
    root.addEventListener("click", instance.clickHandler);
    root.addEventListener("input", instance.inputHandler);
    root.addEventListener("change", instance.inputHandler);
    root.classList.add("xs-ml-ready");
    root.setAttribute("data-xs-ml-ready", "true");
    if (media.provider === "native" || media.provider === "link") {
      instance.provider.mount();
    } else {
      var player = root.querySelector("[data-xs-ml-player]");
      if (player && player.getAttribute("data-xs-ml-autoload") === "true") {
        loadPlayer(instance);
      }
    }
    filter(instance, "register");
    if (!syncUrl(instance) && config.initialAgenda) {
      setCurrent(instance, "agenda", config.initialAgenda, { source: "initial", url: false, announce: false });
    }
    emit(instance, "ready", { duplicateKey: instance.duplicateKey });
    observe();
    return true;
  }

  function destroy(id) {
    var instance = instances[id];
    if (!instance) {
      return false;
    }
    window.clearTimeout(instance.filterTimer);
    instance.root.removeEventListener("click", instance.clickHandler);
    instance.root.removeEventListener("input", instance.inputHandler);
    instance.root.removeEventListener("change", instance.inputHandler);
    instance.provider.destroy();
    if (keyOwners[instance.config.key] === id) {
      delete keyOwners[instance.config.key];
    }
    delete instances[id];
    return true;
  }

  function refresh(id) {
    if (id) {
      var instance = instances[id];
      if (!instance) {
        return false;
      }
      if (!document.documentElement.contains(instance.root)) {
        destroy(id);
        return false;
      }
      filter(instance, "refresh");
      return true;
    }
    registerConfigs();
    Object.keys(instances).forEach(refresh);
    return true;
  }

  function registerConfigs() {
    document.querySelectorAll("[data-xs-ml-config]").forEach(function (element) {
      var id = element.getAttribute("data-xs-ml-config");
      if (!id || instances[id]) {
        return;
      }
      try {
        register(JSON.parse(element.textContent || "{}"));
      } catch (error) {
        // Invalid serialized configuration fails closed without affecting the page.
      }
    });
  }

  function observe() {
    if (observer || !document.body || typeof MutationObserver === "undefined") {
      return;
    }
    observer = new MutationObserver(function () {
      window.clearTimeout(observe.timer);
      observe.timer = window.setTimeout(function () {
        registerConfigs();
        refresh();
      }, 80);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  window.addEventListener("message", function (event) {
    var data = event.data;
    if (typeof data === "string") {
      try {
        data = JSON.parse(data);
      } catch (error) {
        return;
      }
    }
    remotePlayers.forEach(function (provider) {
      if (
        provider.frame
        && provider.frame.contentWindow === event.source
        && provider.origin === event.origin
      ) {
        provider.receive(data);
      }
    });
  });

  function syncAllUrls() {
    Object.keys(instances).forEach(function (id) {
      syncUrl(instances[id]);
    });
  }
  window.addEventListener("popstate", syncAllUrls);
  window.addEventListener("hashchange", syncAllUrls);
  window.addEventListener("pageshow", function () {
    refresh();
    syncAllUrls();
  });

  window.PatchesXsMeetingLens = {
    register: register,
    open: function (id, kind, key) {
      var instance = instances[id];
      return instance ? setCurrent(instance, kind, key, { source: "api", scroll: true }) : false;
    },
    seek: function (id, seconds, options) {
      return instances[id] ? seek(instances[id], seconds, options || {}) : false;
    },
    selectAgenda: function (id, key) {
      return instances[id] ? setCurrent(instances[id], "agenda", key, { source: "api", scroll: true }) : false;
    },
    selectChapter: function (id, key) {
      var instance = instances[id];
      if (!instance) {
        return false;
      }
      var chapter = instance.config.chapters.find(function (entry) {
        return entry.key === key;
      });
      return chapter ? seek(instance, chapter.start, { chapterKey: key, source: "api", url: true }) : false;
    },
    setFollow: function (id, value) {
      if (!instances[id]) {
        return false;
      }
      instances[id].state.follow = Boolean(value);
      return true;
    },
    search: function (id, query) {
      if (!instances[id] || !instances[id].search) {
        return false;
      }
      instances[id].search.value = query || "";
      return filter(instances[id], "api");
    },
    setFilters: function (id, filters) {
      var instance = instances[id];
      if (!instance) {
        return false;
      }
      filters = filters || {};
      if (instance.typeFilter && typeof filters.type === "string") {
        instance.typeFilter.value = filters.type;
      }
      if (instance.statusFilter && typeof filters.status === "string") {
        instance.statusFilter.value = filters.status;
      }
      return filter(instance, "api");
    },
    clearFilters: function (id) {
      return instances[id] ? clearFilters(instances[id]) : false;
    },
    loadPlayer: function (id) {
      return instances[id] ? loadPlayer(instances[id]) : false;
    },
    copyLink: function (id, kind, key) {
      var instance = instances[id];
      if (!instance || !navigator.clipboard) {
        return false;
      }
      var url = new URL(window.location.href);
      if (instance.config.urlMode === "query") {
        url.searchParams.set(instance.config.urlParameter, kind + ":" + key);
      } else {
        url.hash = "meeting-" + instance.config.key + "--" + kind + "-" + key;
      }
      navigator.clipboard.writeText(url.toString()).then(function () {
        announce(instance, "Link copied.");
        emit(instance, "linkcopied", { kind: kind, recordKey: key, url: url.toString() });
      });
      return true;
    },
    print: function (id) {
      if (!instances[id]) {
        return false;
      }
      emit(instances[id], "print", {});
      window.print();
      return true;
    },
    getState: function (id) {
      if (!instances[id]) {
        return null;
      }
      return Object.assign({}, instances[id].state);
    },
    reset: function (id) {
      var instance = instances[id];
      if (!instance) {
        return false;
      }
      clearFilters(instance);
      instance.state.agenda = "";
      instance.state.chapter = "";
      instance.root.querySelectorAll("[aria-current]").forEach(function (record) {
        record.removeAttribute("aria-current");
      });
      return true;
    },
    refresh: refresh,
    destroy: destroy
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", registerConfigs, { once: true });
  } else {
    registerConfigs();
  }
})(window, document);
