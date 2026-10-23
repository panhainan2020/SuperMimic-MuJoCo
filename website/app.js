/* Static metrics; separately hosted media is requested only after a click. */
(() => {
  "use strict";
  const data = window.EVALUATION_DATA;
  if (!data) return;
  const $ = id => document.getElementById(id);
  const text = (id, value) => { $(id).textContent = value; };
  const number = (value, digits = 2) => Number(value).toFixed(digits);
  const time = seconds => `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
  const safeMedia = value => typeof value === "string" && !/^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(value);
  const config = window.MEDIA_CONFIG || {};
  function mediaUrl(key) {
    if (!config.enabled || !key) return null;
    const url = (config.overrides || {})[key] || (config.baseUrl ? config.baseUrl.replace(/\/$/, "") + "/" + key : null);
    if (!url || /[<>\x00-\x1f]/.test(url)) return null;
    // HTTPS public hosts, relative paths, or an explicitly configured local QA server.
    if (/^https:\/\//i.test(url) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(url) || (safeMedia(url) && !url.startsWith("/"))) return url;
    return null;
  }
  if (config.repositoryUrl && /^https:\/\/github\.com\//i.test(config.repositoryUrl)) {
    $("repository-link").href = config.repositoryUrl; $("repository-link").hidden = false;
  }
  const m = data.metrics;
  text("main-score", number(m.return, 4));
  $("score-fill").style.width = `${Math.max(0, Math.min(1, m.return)) * 100}%`;
  text("completion", `${m.nClips - m.nFailed} / ${m.nClips}`);
  text("joint-deg", number(m.jointDeg)); text("body-cm", number(m.alignedBodyCm));
  text("root-cm", number(m.rootCm, 1)); text("end-root", number(m.endRootM));
  text("dataset-description", `${data.dataset.description} 评估关闭域随机化、观测噪声和动作噪声。${data.dataset.scope}`);
  text("dataset-coverage", data.dataset.coverage || "");
  $("csv-link").href = data.links.csv; $("top-report").href = data.links.report; $("metrics-json").href = data.links.metrics;

  const video = $("main-video"), play = $("play-video"), options = $("video-options");
  document.addEventListener("play", event => {
    if (event.target.tagName === "VIDEO") document.querySelectorAll("video").forEach(player => { if (player !== event.target) player.pause(); });
  }, true);
  let selected = null;
  const allVideos = [{...data.overview, label: "全部概览", clip: "70 秒动作概览", category: "overview", isOverview: true}, ...data.videos];
  const videoButtons = [];
  function selectVideo(item, index) {
    video.pause(); video.removeAttribute("src"); video.load();
    selected = item;
    // No poster fetch on selection: first load must not contact the media host.
    video.removeAttribute("poster");
    const available = Boolean(mediaUrl(item.path));
    video.hidden = !available; play.hidden = !available;
    $("media-unavailable").hidden = available; $("video-error").hidden = true;
    text("video-title", item.isOverview ? "70 秒动作概览" : `${item.label} · ${item.clip}`);
    text("video-time", time(item.durationSeconds));
    text("load-size", `${time(item.durationSeconds)} · 点击后加载`);
    text("video-description", item.isOverview ? "七类动作各 10 秒的中段片段；完整过程请切换动作类别。" : "完整记录 · 50 Hz · 从起始帧运行至动作结束");
    text("video-return", item.isOverview ? "概览片段" : `回报 ${number(item.return, 4)}`);
    videoButtons.forEach((button, i) => {
      button.classList.toggle("selected", i === index);
      button.setAttribute("aria-pressed", String(i === index));
    });
  }
  allVideos.forEach((item, index) => {
    const button = document.createElement("button");
    button.type = "button"; button.className = "video-option";
    button.setAttribute("aria-label", `${item.label}，${time(item.durationSeconds)}`);
    const label = document.createElement("span"); label.className = "video-option-label";
    const dot = document.createElement("span"); dot.className = "option-dot"; dot.setAttribute("aria-hidden", "true");
    label.append(dot, document.createTextNode(item.label));
    const duration = document.createElement("small"); duration.textContent = time(item.durationSeconds);
    button.append(label, duration); button.addEventListener("click", () => selectVideo(item, index));
    options.append(button); videoButtons.push(button);
  });
  play.addEventListener("click", async () => {
    if (!selected) return;
    const source = mediaUrl(selected.path); if (!source) return;
    video.src = source; play.hidden = true;
    try { await video.play(); } catch (err) {
      if (err.name !== "AbortError") {
        text("video-error", "视频暂时无法播放，请稍后重试。指标与报告仍可查看。");
        $("video-error").hidden = false;
      }
    }
  });
  video.addEventListener("error", () => {
    if (!video.getAttribute("src")) return;
    text("video-error", "视频暂时不可用。指标与报告仍可查看。");
    $("video-error").hidden = false;
  });
  selectVideo(allVideos[0], 0);

  for (const [key, label] of Object.entries(data.labels)) {
    const option = document.createElement("option"); option.value = key;
    option.textContent = `${label} (${data.clips.filter(clip => clip.category === key).length})`;
    $("category-filter").append(option);
  }
  function renderTable() {
    const query = $("clip-search").value.trim().toLowerCase();
    const category = $("category-filter").value;
    let clips = data.clips.filter(clip => (!query || `${clip.name} ${data.labels[clip.category] || ""}`.toLowerCase().includes(query)) && (category === "all" || clip.category === category));
    const sort = $("sort-order").value;
    clips.sort((a, b) => sort === "return-desc" ? b.return - a.return : sort === "root-desc" ? b.rootCm - a.rootCm : sort === "joint-desc" ? b.jointDeg - a.jointDeg : sort === "name-asc" ? a.name.localeCompare(b.name) : a.return - b.return);
    const fragment = document.createDocumentFragment();
    clips.forEach(clip => {
      const row = document.createElement("tr");
      const nameCell = document.createElement("td"), name = document.createElement("strong"), label = document.createElement("small");
      name.textContent = clip.name; label.textContent = data.labels[clip.category] || clip.category;
      nameCell.append(name, label); row.append(nameCell);
      const values = [number(clip.return, 4), clip.failed ? "提前终止" : "完整完成", `${number(clip.jointDeg)}°`, `${number(clip.alignedBodyCm)} cm`, `${number(clip.rootCm, 1)} cm`, time(clip.durationSeconds)];
      values.forEach((value, index) => {
        const cell = document.createElement("td");
        if (index === 1) { const badge = document.createElement("span"); badge.className = clip.failed ? "failed" : "passed"; badge.textContent = value; cell.append(badge); }
        else { cell.textContent = value; if (index === 0) cell.className = "return-cell"; if (index === 4) cell.className = "root-cell"; }
        row.append(cell);
      });
      fragment.append(row);
    });
    if (!clips.length) { const row = document.createElement("tr"), cell = document.createElement("td"); cell.colSpan = 7; cell.textContent = "没有匹配的动作，请调整搜索条件。"; row.append(cell); fragment.append(row); }
    $("clip-table").replaceChildren(fragment);
    text("table-count", `显示 ${clips.length} / ${data.clips.length} 条动作`);
  }
  $("clip-search").addEventListener("input", renderTable);
  $("category-filter").addEventListener("change", renderTable);
  $("sort-order").addEventListener("change", renderTable); renderTable();

  const ood = data.ood || {status: "pending"};
  text("ood-title", ood.title || "100STYLE 分布外测试");
  const complete = ["complete", "completed", "partial"].includes(ood.status);
  const statusLabels = {complete: "评估完成", completed: "评估完成", partial: "部分结果", running: "评估中", pending: "待评估", blocked: "尚未完成"};
  text("ood-status", statusLabels[ood.status] || "待评估");
  $("ood-status").className = `status ${complete ? "success" : "pending"}`;
  const content = $("ood-content"); content.replaceChildren();
  const addParagraph = (value, className = "") => { if (value) { const node = document.createElement("p"); node.textContent = value; node.className = className; content.append(node); } };
  addParagraph(ood.headline || (complete ? "冻结 LAFAN1 策略，评估训练库以外的动作。" : "训练库以外的动作，需要独立测试。"), "ood-heading");
  addParagraph(ood.scope || "使用同一冻结策略开展 100STYLE 测试；不把本页的 LAFAN1 结果替代分布外结果。");
  const entries = [["评估动作数", ood.n_clips], ["覆盖风格数", ood.n_styles], ["平均归一化回报", ood.normalized_return == null ? null : number(ood.normalized_return, 4)], ["提前终止动作", ood.n_failed]];
  if (complete && entries.some(entry => entry[1] != null)) {
    const grid = document.createElement("div"); grid.className = "ood-grid";
    entries.filter(entry => entry[1] != null).forEach(([label, value]) => { const item = document.createElement("div"); item.className = "ood-metric"; const name = document.createElement("span"), metric = document.createElement("strong"); name.textContent = label; metric.textContent = value; item.append(name, metric); grid.append(item); });
    content.append(grid);
  }
  if (complete) {
    addParagraph("短片段重置更频繁，且动作来源与重定向处理不同。以下是同一冻结策略的描述性对照，两组结果不能视为相同难度的比较。", "ood-caution");
  }
  if (complete && ood.comparison && ood.comparison.id && ood.comparison.ood) {
    const comparison = ood.comparison;
    const wrap = document.createElement("div"); wrap.className = "comparison-wrap";
    const table = document.createElement("table"); table.className = "comparison-table"; table.id = "comparison-table";
    const head = document.createElement("thead"), header = document.createElement("tr");
    ["同一冻结策略 · 每片段等权", "LAFAN1 / 训练库内", "100STYLE / 分布外"].forEach(value => { const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = value; header.append(cell); }); head.append(header);
    const body = document.createElement("tbody");
    const id = comparison.id, out = comparison.ood;
    const rows = [
      ["平均归一化回报 ↑", number(id.normalized_return, 4), number(out.normalized_return, 4)],
      ["片段完成率 ↑", `${number(100 * id.success_fraction)}% (${id.n_clips - id.n_failed}/${id.n_clips})`, `${number(100 * out.success_fraction)}% (${out.n_clips - out.n_failed}/${out.n_clips})`],
      ["关节角平均误差 ↓", `${number(id.tracking_clip_equal_weighted.joint_mae_deg)}°`, `${number(out.tracking_clip_equal_weighted.joint_mae_deg)}°`],
      ["对齐后身体位置误差 ↓", `${number(100 * id.tracking_clip_equal_weighted.tracked_body_xy_yaw_anchored_mpjpe_m)} cm`, `${number(100 * out.tracking_clip_equal_weighted.tracked_body_xy_yaw_anchored_mpjpe_m)} cm`],
      ["平均连续片段时长", `${number(id.mean_clip_duration_seconds)} s`, `${number(out.mean_segment_duration_seconds)} s`],
    ];
    rows.forEach(values => { const row = document.createElement("tr"); values.forEach(value => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); body.append(row); });
    table.append(head, body); wrap.append(table); content.append(wrap);
    addParagraph("姿态误差仅统计存活步；对齐后的身体误差不等于全局路径误差。LAFAN1 的 0.82 复现目标不作为 100STYLE 通过线。", "ood-table-note");
  }
  if (Array.isArray(ood.notes) && ood.notes.length) {
    const details = document.createElement("details"); details.className = "ood-details";
    const summary = document.createElement("summary"); summary.textContent = "数据范围与评估条件";
    const notes = document.createElement("ul"); notes.className = "ood-notes";
    ood.notes.forEach(note => { const item = document.createElement("li"); item.textContent = note.replace(/成功率/g, "完成率"); notes.append(item); }); details.append(summary, notes); content.append(details);
  }
  if (Array.isArray(ood.links) && ood.links.length) {
    const links = document.createElement("div"); links.className = "ood-links";
    ood.links.filter(item => safeMedia(item.path)).forEach(item => { const link = document.createElement("a"); link.href = item.path; link.textContent = `${item.label} ↗`; links.append(link); }); content.append(links);
    if (ood.sourceUrl && /^https:\/\//i.test(ood.sourceUrl)) { const link = document.createElement("a"); link.href = ood.sourceUrl; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = "G1 分段数据来源 ↗"; links.append(link); }
  }
  if (Array.isArray(ood.videos) && ood.videos.length) {
    const sectionTitle = document.createElement("h3"); sectionTitle.className = "ood-subheading"; sectionTitle.textContent = "分布外动作 · 代表片段与失败例"; content.append(sectionTitle);
    const media = document.createElement("div"); media.className = "ood-media";
    ood.videos.filter(item => safeMedia(item.path)).forEach(item => {
      const article = document.createElement("article"); article.className = "ood-media-item";
      const heading = document.createElement("h3"); heading.textContent = (item.title || item.clip || "100STYLE 动作").replace(/成功片段/g, "完整片段");
      const meta = document.createElement("div"); meta.className = "ood-video-meta";
      const badge = document.createElement("span"); badge.className = item.failed ? "failed" : "passed"; badge.textContent = item.failed ? "提前终止" : "完整完成";
      const score = document.createElement("span"); score.textContent = `回报 ${number(item.normalized_return, 4)}`;
      meta.append(badge, score);
      const player = document.createElement("video"); player.controls = true; player.preload = "none"; player.playsInline = true;
      player.setAttribute("aria-label", item.title || item.clip || "100STYLE 动作");
      const source = mediaUrl(item.path);
      const duration = document.createElement("p"); duration.className = "ood-video-duration"; duration.textContent = `实际 ${number(item.duration_seconds)} s / 参考 ${number(item.reference_duration_seconds)} s`;
      const button = document.createElement("button"); button.type = "button"; button.textContent = "加载并播放";
      button.addEventListener("click", async () => { video.pause(); if (!player.getAttribute("src") && source) player.src = source; try { await player.play(); button.hidden = true; } catch { button.textContent = "重试播放"; } });
      article.append(heading, meta);
      if (source) article.append(player, duration, button);
      else { const unavailable = document.createElement("p"); unavailable.className = "media-unavailable"; unavailable.textContent = "该片段暂未公开，指标见下表。 / Video not published."; article.append(unavailable, duration); }
      media.append(article);
    }); content.append(media);
  }
  if (Array.isArray(ood.styles) && ood.styles.length) {
    const sectionTitle = document.createElement("h3"); sectionTitle.className = "ood-subheading"; sectionTitle.textContent = "100 种风格 · 逐类查看"; content.append(sectionTitle);
    const tools = document.createElement("div"); tools.className = "table-tools style-tools";
    const searchLabel = document.createElement("label"); searchLabel.className = "search-field";
    const search = document.createElement("input"); search.id = "style-search"; search.type = "search"; search.placeholder = "搜索风格，如 Flapping、Old…"; search.setAttribute("aria-label", "搜索100STYLE风格"); searchLabel.append(search);
    const sortLabel = document.createElement("label"); sortLabel.className = "filter-field";
    const sort = document.createElement("select"); sort.id = "style-sort"; sort.setAttribute("aria-label", "风格排序方式");
    [["return-asc", "回报：从低到高"], ["return-desc", "回报：从高到低"], ["failed-desc", "失败数：从多到少"], ["name-asc", "风格名称"]].forEach(([value, label]) => { const option = document.createElement("option"); option.value = value; option.textContent = label; sort.append(option); }); sortLabel.append(sort); tools.append(searchLabel, sortLabel); content.append(tools);
    const wrap = document.createElement("div"); wrap.className = "table-wrap style-table-wrap"; wrap.tabIndex = 0; wrap.setAttribute("aria-label", "100STYLE 风格汇总指标，可横向滚动");
    const table = document.createElement("table"), head = document.createElement("thead"), header = document.createElement("tr"), body = document.createElement("tbody"); body.id = "style-table";
    ["风格", "片段数", "回报 ↑", "提前终止", "完成率 ↑", "关节误差 ↓", "对齐身体误差 ↓"].forEach(value => { const cell = document.createElement("th"); cell.scope = "col"; cell.textContent = value; header.append(cell); }); head.append(header); table.append(head, body); wrap.append(table); content.append(wrap);
    const foot = document.createElement("div"); foot.className = "table-footer"; const count = document.createElement("span"); count.id = "style-count"; count.setAttribute("aria-live", "polite"); const note = document.createElement("span"); note.textContent = "每风格内片段等权 · 回报汇总自逐片段四位小数"; foot.append(count, note); content.append(foot);
    function renderStyles() {
      const query = search.value.trim().toLowerCase();
      const styles = ood.styles.filter(style => style.name.toLowerCase().includes(query));
      styles.sort((a, b) => sort.value === "return-desc" ? b.return - a.return : sort.value === "failed-desc" ? b.nFailed - a.nFailed || a.return - b.return : sort.value === "name-asc" ? a.name.localeCompare(b.name) : a.return - b.return);
      const fragment = document.createDocumentFragment();
      styles.forEach(style => { const row = document.createElement("tr"); const values = [style.name, style.nClips, number(style.return, 4), style.nFailed, `${number(100 * style.successFraction)}%`, `${number(style.jointDeg)}°`, `${number(style.alignedBodyCm)} cm`]; values.forEach((value, index) => { const cell = document.createElement("td"); cell.textContent = value; if (index === 2) cell.className = "return-cell"; if (index === 3 && style.nFailed > 0) cell.className = "failure-count"; row.append(cell); }); fragment.append(row); });
      if (!styles.length) { const row = document.createElement("tr"), cell = document.createElement("td"); cell.colSpan = 7; cell.textContent = "没有匹配的风格，请调整搜索条件。"; row.append(cell); fragment.append(row); }
      body.replaceChildren(fragment); count.textContent = `显示 ${styles.length} / ${ood.styles.length} 种风格`;
    }
    search.addEventListener("input", renderStyles); sort.addEventListener("change", renderStyles); renderStyles();
  }
})();
