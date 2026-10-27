// 在首帧之前套上用户上次选的氛围，避免浅色主题先闪一下深色。
(function () {
  var ok = { forest: 1, midnight: 1, paper: 1, peach: 1, mist: 1 };
  var t = "forest";
  try { t = localStorage.getItem("xg-theme") || "forest"; } catch (e) {}
  document.documentElement.setAttribute("data-theme", ok[t] ? t : "forest");
})();
