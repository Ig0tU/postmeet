document.getElementById("open").addEventListener("click", () => {
  chrome.tabs.create({ url: "https://postmeet-mu.vercel.app" });
});
