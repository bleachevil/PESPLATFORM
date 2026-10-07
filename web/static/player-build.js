(function () {
  var dataEl = document.getElementById("player-build-data");
  if (!dataEl) return;
  var build;
  try {
    build = JSON.parse(dataEl.textContent || "{}");
  } catch (err) {
    return;
  }
  var stats = build.stats || [];
  var boosters = {};
  (build.boosters || []).forEach(function (item) {
    boosters[item.id] = item.bonuses || {};
  });

  var levelInput = document.getElementById("level-slider");
  var progInput = document.getElementById("prog-slider");
  var boosterA = document.getElementById("booster-a");
  var boosterB = document.getElementById("booster-b");
  var cap = 99;

  function clamp(value) {
    return Math.max(0, Math.min(cap, value));
  }

  function currentLevel() {
    if (!levelInput) return build.level || 1;
    return Number(levelInput.value);
  }

  function progPoints() {
    if (!progInput) return 0;
    return Number(progInput.value) || 0;
  }

  function levelFactor(level) {
    var maxLevel = build.maxLevel || 1;
    var minLevel = build.level || 1;
    if (maxLevel <= minLevel) return 0;
    return (level - minLevel) / (maxLevel - minLevel);
  }

  function allocation(points) {
    var grown = stats
      .filter(function (stat) {
        return !stat.hidden && stat.max > stat.base;
      })
      .sort(function (a, b) {
        return b.max - b.base - (a.max - a.base);
      })
      .map(function (stat) {
        return stat.key;
      });
    var extra = {};
    var i = 0;
    while (points > 0 && grown.length) {
      extra[grown[i]] = (extra[grown[i]] || 0) + 1;
      points -= 1;
      i = (i + 1) % grown.length;
    }
    return extra;
  }

  function activeBonuses() {
    var bonuses = {};
    [boosterA, boosterB].forEach(function (el) {
      if (!el || !el.value) return;
      var pack = boosters[el.value] || {};
      Object.keys(pack).forEach(function (key) {
        bonuses[key] = (bonuses[key] || 0) + pack[key];
      });
    });
    return bonuses;
  }

  function render() {
    var level = currentLevel();
    var t = levelFactor(level);
    var liveOvr = Math.round(build.overall + (build.maxOverall - build.overall) * t);
    var bonuses = activeBonuses();
    var extra = allocation(progPoints());
    if (boosterA && boosterA.value) liveOvr += 2;
    if (boosterB && boosterB.value) liveOvr += 2;
    liveOvr += Math.round(progPoints() * 0.25);

    var levelLabel = document.getElementById("level-label");
    var liveLevel = document.getElementById("live-level");
    var liveOvrEl = document.getElementById("live-ovr");
    var progLabel = document.getElementById("prog-label");
    var summary = document.getElementById("build-summary");
    if (levelLabel) levelLabel.textContent = String(level);
    if (liveLevel) liveLevel.textContent = String(level);
    if (liveOvrEl) liveOvrEl.textContent = String(liveOvr);
    if (progLabel) progLabel.textContent = String(progPoints());
    if (summary) {
      var bits = ["Level " + level];
      if (progPoints()) bits.push(progPoints() + " progression");
      if ((boosterA && boosterA.value) || (boosterB && boosterB.value)) bits.push("booster on");
      summary.textContent = bits.join(" · ") + " · OVR " + liveOvr + " / MAX " + build.maxOverall;
    }

    var areaGain = { attack: 0, defence: 0, strength: 0 };
    stats.forEach(function (stat) {
      if (stat.hidden) return;
      var grown = Math.round(stat.base + (stat.max - stat.base) * t);
      var shown = clamp(grown + (bonuses[stat.key] || 0) + (extra[stat.key] || 0));
      var gain = shown - stat.base;
      areaGain[stat.group] += Math.max(0, gain);
      var row = document.querySelector('.stat-row[data-key="' + stat.key + '"]');
      if (!row) return;
      var now = row.querySelector(".now-fill");
      var incrFill = row.querySelector(".incr-fill");
      var nowLabel = row.querySelector(".stat-now");
      var maxShown = clamp(stat.max + (bonuses[stat.key] || 0) + (extra[stat.key] || 0));
      if (now) now.style.width = Math.min(cap, shown) + "%";
      if (incrFill) incrFill.style.width = Math.min(cap, maxShown) + "%";
      if (nowLabel) nowLabel.textContent = String(shown);
    });
    Object.keys(areaGain).forEach(function (group) {
      var el = document.querySelector('.area-incr[data-area="' + group + '"]');
      if (el) el.textContent = "+" + areaGain[group];
    });
  }

  if (levelInput) levelInput.addEventListener("input", render);
  if (progInput) progInput.addEventListener("input", render);
  if (boosterA) boosterA.addEventListener("change", render);
  if (boosterB) boosterB.addEventListener("change", render);
  var maxBtn = document.getElementById("max-build");
  if (maxBtn) {
    maxBtn.addEventListener("click", function () {
      if (levelInput) levelInput.value = String(build.maxLevel);
      if (progInput) progInput.value = String(build.progressionPoints || 0);
      if (boosterA && !boosterA.value && boosterA.options.length > 1) boosterA.selectedIndex = 1;
      render();
    });
  }
  render();
})();
