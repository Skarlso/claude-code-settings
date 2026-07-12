# 可视化伴侣指南

基于浏览器的头脑风暴可视化伴侣，用于展示 mockup、图表和方案对比。

**脚本路径：** 下文中所有 `scripts/` 路径均相对于本 skill 目录。运行前请解析为绝对路径（例如本 skill 位于 `~/.claude/skills/brainstorming/`，则脚本在 `~/.claude/skills/brainstorming/scripts/`）。

## 何时使用

逐个问题判断，而非按会话决定。判断标准：**用户看到它会不会比读到它理解得更好？**

**用浏览器** 展示本质是视觉的内容：

- **UI mockup** — 线框图、布局、导航结构、组件设计
- **架构图** — 系统组件、数据流、关系图
- **并排视觉对比** — 两种布局、两种配色、两种设计方向的对比
- **设计打磨** — 关于外观、间距、视觉层次的问题
- **空间关系** — 状态机、流程图、实体关系图

**用终端** 展示本质是文字或表格的内容：

- **需求和范围问题** — "X 是什么意思？"、"哪些功能在范围内？"
- **概念上的 A/B/C 选择** — 用文字描述即可的方案比较
- **权衡列表** — 优劣对比、比较表格
- **技术决策** — API 设计、数据建模、架构方案选择
- **澄清性问题** — 答案是文字而非视觉偏好的任何问题

关于 UI 话题的问题不自动等于视觉问题。"你想要什么样的向导？"是概念问题——用终端。"这几种向导布局哪个更合适？"是视觉问题——用浏览器。

## 工作原理

服务器监控一个目录中的 HTML 文件，将最新的文件推送到浏览器。你将 HTML 内容写入 `screen_dir`，用户在浏览器中看到并可以点击选项。点击记录保存到 `state_dir/events`，你在下一轮读取。

**内容片段 vs 完整文档：** 如果你的 HTML 文件以 `<!DOCTYPE` 或 `<html` 开头，服务器原样提供（仅注入 helper 脚本）。否则，服务器自动用框架模板包裹你的内容——添加页头、CSS 主题、连接状态和所有交互基础设施。**默认写内容片段。** 只有需要完全控制页面时才写完整文档。

## 启动会话

```bash
# 用户同意后启动。--open 自动打开浏览器；--project-dir 持久化 mockup 并支持同端口重启。
scripts/start-server.sh --project-dir /path/to/project --open

# 返回：{"type":"server-started","port":52341,
#        "url":"http://localhost:52341/?key=ab12…",
#        "screen_dir":"/path/to/project/.brainstorm/12345-1706000000/content",
#        "state_dir":"/path/to/project/.brainstorm/12345-1706000000/state"}
```

保存返回的 `screen_dir` 和 `state_dir`。使用 `--open` 时，推送第一个页面后浏览器自动打开——无需让用户手动打开，但仍应提供 URL 作为备用（headless/远程环境不会自动打开）。

**URL 包含会话密钥（`?key=…`）。** 服务器拒绝不带密钥的请求，因此务必将 `url` 字段的**完整** URL 给用户——不要去掉查询参数，不要只给 `http://host:port`。密钥保护 HTTP 和 WebSocket 访问，防止其他浏览器标签页或网络上的其他设备读取页面或注入事件。首次加载后浏览器通过 cookie 记住密钥，后续刷新和 `/files/*` 资源无需重复。

**查找连接信息：** 服务器将启动 JSON 写入 `$STATE_DIR/server-info`。如果在后台启动且未捕获 stdout，读取该文件获取 URL 和端口。使用 `--project-dir` 时，查看 `<project>/.brainstorm/` 找到会话目录。

**注意：** 传入项目根目录作为 `--project-dir`，这样 mockup 文件会持久化在 `.brainstorm/` 中，服务器重启后仍在。不传则文件存入 `/tmp` 并被清理。提醒用户将 `.brainstorm/` 加入 `.gitignore`。

**各平台启动方式：**

**Claude Code：**
```bash
# 默认即可——脚本自行将服务器放到后台。
scripts/start-server.sh --project-dir /path/to/project --open
```

Windows 下脚本自动切换为前台模式（会阻塞 tool call）。对 Bash tool call 使用 `run_in_background: true` 让服务器跨对话轮次存活，然后在下一轮读取 `$STATE_DIR/server-info` 获取 URL 和端口。

**Codex：**
```bash
# Codex 会回收后台进程。脚本自动检测 CODEX_CI 并切换为前台模式。正常运行即可。
scripts/start-server.sh --project-dir /path/to/project --open
```

**Copilot CLI：**
```bash
# 使用 --foreground 并通过 bash tool 的 mode: "async" 启动，
# 使进程跨对话轮次存活。保存返回的 shellId 以便后续 read_bash / stop_bash。
scripts/start-server.sh --project-dir /path/to/project --open --foreground
```

**其他环境：** 服务器需要在对话轮次之间持续运行。如果你的环境会回收后台进程，使用 `--foreground` 并通过平台的后台执行机制启动。

如果 URL 从浏览器不可达（远程/容器化环境常见），绑定非回环地址：

```bash
scripts/start-server.sh \
  --project-dir /path/to/project \
  --host 0.0.0.0 \
  --url-host localhost
```

使用 `--url-host` 控制返回 URL 中的主机名。

## 循环流程

1. **确认服务器存活**，然后**写 HTML** 到 `screen_dir` 中的新文件：
   - **必须：推送页面或引用 URL 之前先确认服务器存活。** 检查 `$STATE_DIR/server-info` 存在且 `$STATE_DIR/server-stopped` 不存在。如果已关闭，用相同的 `--project-dir` 运行 `start-server.sh` 重启——会复用同一端口，用户已打开的标签页自动重连（服务器离线期间显示"暂停"遮罩），无需发送新 URL。服务器闲置 4 小时自动退出（可通过 `--idle-timeout-minutes` 配置）。
   - 使用语义化文件名：`platform.html`、`visual-style.html`、`layout.html`
   - **不要复用文件名** — 每个页面用新文件
   - 使用文件创建工具 — **不要用 cat/heredoc**（会在终端输出杂乱内容）
   - 服务器自动推送最新文件

2. **告诉用户页面内容并结束你的回合：**
   - 每步都提醒 URL（不只是第一次）
   - 简要描述页面上的内容（例如"展示了 3 种首页布局方案"）
   - 请用户在终端回复："看一下，觉得怎样就告诉我。也可以点击选择某个方案。"

3. **下一轮** — 用户在终端回复后：
   - 读取 `$STATE_DIR/events`（如存在）— 包含用户在浏览器中的交互（点击、选择），每行一个 JSON 对象
   - 结合用户的终端文字，获得完整反馈
   - 终端消息是主要反馈；`state_dir/events` 提供结构化交互数据

4. **迭代或推进** — 如果反馈需要修改当前页面，写新文件（如 `layout-v2.html`）。只有当前步骤确认后才进入下一个问题。

5. **回到终端时卸载页面** — 当下一步不需要浏览器时（如澄清性问题、权衡讨论），推送一个等待页面清除过时内容：

   ```html
   <!-- 文件名：waiting.html（或 waiting-2.html 等）-->
   <div style="display:flex;align-items:center;justify-content:center;min-height:60vh">
     <p class="subtitle">对话在终端继续中...</p>
   </div>
   ```

   避免用户盯着已解决的选项而对话已经继续。下一个视觉问题出现时，照常推送新内容文件。

6. 重复直到完成。

## 编写内容片段

只写放在页面内部的内容。服务器自动用框架模板包裹（页头、主题 CSS、连接状态和所有交互基础设施）。

**最简示例：**

```html
<h2>哪种布局更好？</h2>
<p class="subtitle">考虑可读性和视觉层次</p>

<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>单栏</h3>
      <p>简洁、专注的阅读体验</p>
    </div>
  </div>
  <div class="option" data-choice="b" onclick="toggleSelect(this)">
    <div class="letter">B</div>
    <div class="content">
      <h3>双栏</h3>
      <p>侧边导航加主内容区</p>
    </div>
  </div>
</div>
```

就这些。不需要 `<html>`、CSS 或 `<script>` 标签，服务器已全部提供。

## 可用的 CSS 类

框架模板提供以下 CSS 类供内容使用：

### 选项（A/B/C 选择）

```html
<div class="options">
  <div class="option" data-choice="a" onclick="toggleSelect(this)">
    <div class="letter">A</div>
    <div class="content">
      <h3>标题</h3>
      <p>描述</p>
    </div>
  </div>
</div>
```

**多选：** 在容器上添加 `data-multiselect` 允许用户选择多个选项。每次点击切换选中状态。

```html
<div class="options" data-multiselect>
  <!-- 同样的选项结构——用户可选择/取消多个 -->
</div>
```

### 卡片（视觉设计）

```html
<div class="cards">
  <div class="card" data-choice="design1" onclick="toggleSelect(this)">
    <div class="card-image"><!-- mockup 内容 --></div>
    <div class="card-body">
      <h3>名称</h3>
      <p>描述</p>
    </div>
  </div>
</div>
```

### Mockup 容器

```html
<div class="mockup">
  <div class="mockup-header">预览：仪表盘布局</div>
  <div class="mockup-body"><!-- 你的 mockup HTML --></div>
</div>
```

### 分屏视图（并排对比）

```html
<div class="split">
  <div class="mockup"><!-- 左侧 --></div>
  <div class="mockup"><!-- 右侧 --></div>
</div>
```

### 优劣对比

```html
<div class="pros-cons">
  <div class="pros"><h4>优势</h4><ul><li>好处</li></ul></div>
  <div class="cons"><h4>劣势</h4><ul><li>不足</li></ul></div>
</div>
```

### Mock 元素（线框图构建块）

```html
<div class="mock-nav">Logo | 首页 | 关于 | 联系</div>
<div style="display: flex;">
  <div class="mock-sidebar">导航</div>
  <div class="mock-content">主内容区</div>
</div>
<button class="mock-button">操作按钮</button>
<input class="mock-input" placeholder="输入框">
<div class="placeholder">占位区域</div>
```

### 排版和分区

- `h2` — 页面标题
- `h3` — 章节标题
- `.subtitle` — 标题下方的辅助文字
- `.section` — 带底部间距的内容块
- `.label` — 小号大写标签文字

## 浏览器事件格式

用户在浏览器中点击选项时，交互记录保存到 `$STATE_DIR/events`（每行一个 JSON 对象）。推送新页面时文件自动清空。

```jsonl
{"type":"click","choice":"a","text":"方案 A - 简洁布局","timestamp":1706000101}
{"type":"click","choice":"c","text":"方案 C - 复杂网格","timestamp":1706000108}
{"type":"click","choice":"b","text":"方案 B - 混合布局","timestamp":1706000115}
```

完整事件流展示了用户的探索路径——他们可能点了多个选项才最终确定。最后一个 `choice` 事件通常是最终选择，但点击模式可能揭示犹豫或值得追问的偏好。

如果 `$STATE_DIR/events` 不存在，说明用户没有在浏览器中交互——只用终端文字。

## 设计建议

- **保真度匹配问题类型** — 布局问题用线框图，打磨问题用精细设计
- **每个页面都解释问题** — "哪种布局更专业？"而不是"选一个"
- **确认后再推进** — 如果反馈要修改当前页面，先写新版本
- **每页 2-4 个选项**
- **在需要时使用真实内容** — 比如摄影作品集用真实图片（Unsplash）。占位内容会掩盖设计问题
- **mockup 保持简洁** — 关注布局和结构，不追求像素级精确

## 文件命名

- 使用语义化名称：`platform.html`、`visual-style.html`、`layout.html`
- 不要复用文件名——每个页面必须是新文件
- 迭代版本加后缀：`layout-v2.html`、`layout-v3.html`
- 服务器按修改时间推送最新文件

## 清理

```bash
scripts/stop-server.sh $SESSION_DIR
```

如果会话使用了 `--project-dir`，mockup 文件保留在 `.brainstorm/` 中供后续参考。只有 `/tmp` 会话在停止时被删除。

## 参考

- 框架模板（CSS 参考）：`scripts/frame-template.html`
- Helper 脚本（客户端）：`scripts/helper.js`
