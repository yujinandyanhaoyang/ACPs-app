# Reading Concierge Web Demo — Codex 工程化改造任务

> **使用方式**：将本文件完整粘贴给 Codex，并附上项目当前目录树与技术栈说明。
> 每个 Phase 是独立的 Codex 会话任务，按顺序执行，前一个 Phase 完成并通过验收后再启动下一个。

---

## 项目上下文（你需要填写）

```
项目根目录结构：
<在此粘贴 tree 命令输出>

前端技术栈：
<原生 HTML/CSS/JS | Vue 3 | React 18 | 其他>

现有后端 API base_url：
<http://localhost:8000 | 其他>

现有 web_demo 入口文件：
<web_demo/index.html | 其他>

需要保留不改动的文件/目录：
<列出>
```

---

## 全局约束（所有 Phase 适用）

1. **不引入任何 CSS 框架**（禁止 Tailwind / Bootstrap / UnoCSS）
2. **不引入前端框架**（除非项目已有；若有 Vue/React，在对应 Phase 说明）
3. 所有颜色、间距、圆角、字号必须通过 CSS Custom Properties 引用，**禁止在组件样式中写硬编码颜色值**
4. 所有数字/分数显示必须加 `font-variant-numeric: tabular-nums`
5. 暗色模式通过 `[data-theme="dark"]` attribute 切换，不能只靠 `prefers-color-scheme`
6. 每个 Phase 完成后，在控制台输出 `PHASE_X_DONE` 标记，便于验收
7. 不能删除现有后端调用逻辑，只能在其上方增加 UI 层

---

## Phase 1 — 设计系统基础层

**目标**：建立完整的 Design Token 系统，不修改任何业务逻辑。

### 任务 1.1 — 创建 `styles/tokens.css`

创建文件 `web_demo/styles/tokens.css`，内容如下：

```css
/* ─── Light Theme ─── */
:root, [data-theme="light"] {
  /* Surfaces */
  --color-bg:                #f7f6f2;
  --color-surface:           #f9f8f5;
  --color-surface-2:         #fbfbf9;
  --color-surface-offset:    #f0ede8;
  --color-divider:           #dcd9d5;
  --color-border:            #d4d1ca;

  /* Text */
  --color-text:              #28251d;
  --color-text-muted:        #7a7974;
  --color-text-faint:        #bab9b4;

  /* Brand */
  --color-primary:           #01696f;
  --color-primary-hover:     #0c4e54;
  --color-primary-highlight: #cedcd8;

  /* Semantic */
  --color-success:           #437a22;
  --color-success-highlight: #d4dfcc;
  --color-warning:           #964219;
  --color-warning-highlight: #ddcfc6;
  --color-error:             #a12c7b;
  --color-error-highlight:   #e0ced7;
  --color-gold:              #d19900;
  --color-gold-highlight:    #e9e0c6;

  /* Spacing */
  --space-1: 0.25rem;  --space-2: 0.5rem;   --space-3: 0.75rem;
  --space-4: 1rem;     --space-5: 1.25rem;  --space-6: 1.5rem;
  --space-8: 2rem;     --space-10: 2.5rem;  --space-12: 3rem;
  --space-16: 4rem;

  /* Radius */
  --radius-sm:   0.375rem;
  --radius-md:   0.5rem;
  --radius-lg:   0.75rem;
  --radius-xl:   1rem;
  --radius-full: 9999px;

  /* Shadow */
  --shadow-sm: 0 1px 2px oklch(0.2 0.01 80 / 0.06);
  --shadow-md: 0 4px 12px oklch(0.2 0.01 80 / 0.08);
  --shadow-lg: 0 12px 32px oklch(0.2 0.01 80 / 0.12);

  /* Typography */
  --font-display: 'Instrument Serif', Georgia, serif;
  --font-body:    'Inter', 'Helvetica Neue', sans-serif;

  --text-xs:   clamp(0.75rem,  0.7rem  + 0.25vw, 0.875rem);
  --text-sm:   clamp(0.875rem, 0.8rem  + 0.35vw, 1rem);
  --text-base: clamp(1rem,     0.95rem + 0.25vw, 1.125rem);
  --text-lg:   clamp(1.125rem, 1rem    + 0.75vw, 1.5rem);
  --text-xl:   clamp(1.5rem,   1.2rem  + 1.25vw, 2.25rem);

  /* Motion */
  --transition: 180ms cubic-bezier(0.16, 1, 0.3, 1);
}

/* ─── Dark Theme ─── */
[data-theme="dark"] {
  --color-bg:                #171614;
  --color-surface:           #1c1b19;
  --color-surface-2:         #201f1d;
  --color-surface-offset:    #22211f;
  --color-divider:           #262523;
  --color-border:            #393836;
  --color-text:              #cdccca;
  --color-text-muted:        #797876;
  --color-text-faint:        #5a5957;
  --color-primary:           #4f98a3;
  --color-primary-hover:     #227f8b;
  --color-primary-highlight: #313b3b;
  --color-success:           #6daa45;
  --color-success-highlight: #3a4435;
  --color-warning:           #bb653b;
  --color-warning-highlight: #564942;
  --color-error:             #d163a7;
  --color-error-highlight:   #4c3d46;
  --color-gold:              #e8af34;
  --color-gold-highlight:    #4d4332;
  --shadow-sm: 0 1px 2px oklch(0 0 0 / 0.2);
  --shadow-md: 0 4px 12px oklch(0 0 0 / 0.3);
  --shadow-lg: 0 12px 32px oklch(0 0 0 / 0.4);
}

/* ─── Reduced Motion ─── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 任务 1.2 — 创建 `styles/base.css`

```css
/* Reset + base */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { -webkit-font-smoothing: antialiased; scroll-behavior: smooth; }
body {
  min-height: 100dvh;
  font-family: var(--font-body);
  font-size: var(--text-sm);
  color: var(--color-text);
  background: var(--color-bg);
  line-height: 1.6;
}
img { display: block; max-width: 100%; }
button { cursor: pointer; background: none; border: none; font: inherit; color: inherit; }
input, select, textarea { font: inherit; color: inherit; }
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 3px;
  border-radius: var(--radius-sm);
}
```

### 任务 1.3 — 在 `index.html` 中引入字体和样式

在 `<head>` 最前面插入（如已有则跳过）：
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300..600&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles/tokens.css">
<link rel="stylesheet" href="styles/base.css">
```

### 任务 1.4 — 暗色模式切换 JS

在 `js/theme.js` 中创建（不修改其他 JS 文件）：
```javascript
(function () {
  const root = document.documentElement;
  const stored = localStorage.getItem('theme');
  const preferred = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  let current = stored || preferred;
  root.setAttribute('data-theme', current);

  function toggle() {
    current = current === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', current);
    localStorage.setItem('theme', current);
    document.querySelectorAll('[data-theme-toggle]').forEach(updateIcon);
  }

  function updateIcon(btn) {
    btn.innerHTML = current === 'dark'
      ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
      updateIcon(btn);
      btn.addEventListener('click', toggle);
    });
  });
})();
```

### Phase 1 验收检查
- [ ] `styles/tokens.css` 存在，所有变量正常生效
- [ ] Light/Dark 切换正常，LocalStorage 记忆
- [ ] 页面文字、背景颜色已使用 token 变量（不再有裸色值）
- [ ] 控制台无报错

---

## Phase 2 — 页面骨架与布局

**目标**：搭建 TopBar + Sidebar + 主内容区三栏布局，不实现任何业务功能。

### 任务 2.1 — 创建 `styles/layout.css`

```css
/* ─── App Shell ─── */
.app { display: grid; grid-template-rows: auto 1fr; min-height: 100dvh; }

/* ─── TopBar ─── */
.topbar {
  position: sticky; top: 0; z-index: 100;
  background: color-mix(in oklch, var(--color-surface) 92%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-divider);
  padding: var(--space-3) var(--space-6);
  display: flex; align-items: center; justify-content: space-between; gap: var(--space-4);
  height: 49px;
}
.topbar-brand {
  display: flex; align-items: center; gap: var(--space-3);
}
.topbar-brand .logo-text {
  font-family: var(--font-display); font-style: italic;
  font-size: var(--text-lg); line-height: 1; color: var(--color-text);
}
.topbar-actions { display: flex; align-items: center; gap: var(--space-3); }

/* ─── Main Grid ─── */
.main { display: grid; grid-template-columns: 280px 1fr; }

/* ─── Sidebar ─── */
.sidebar {
  border-right: 1px solid var(--color-divider);
  background: var(--color-surface);
  padding: var(--space-6);
  display: flex; flex-direction: column; gap: var(--space-6);
  height: calc(100dvh - 49px);
  overflow-y: auto;
  position: sticky; top: 49px;
}

/* ─── Content ─── */
.content {
  padding: var(--space-6);
  display: flex; flex-direction: column; gap: var(--space-5);
  max-width: 760px;
}

/* ─── Responsive ─── */
@media (max-width: 900px) {
  .main { grid-template-columns: 1fr; }
  .sidebar {
    height: auto; position: static;
    border-right: none; border-bottom: 1px solid var(--color-divider);
  }
}
```

### 任务 2.2 — 改造 `index.html` 骨架结构

将现有 HTML body 内容包裹进以下结构（保留原有内容在 `.content` 内）：

```html
<div class="app">
  <header class="topbar">
    <!-- 左：Logo -->
    <div class="topbar-brand">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <rect width="28" height="28" rx="8" fill="var(--color-primary)"/>
        <path d="M7 9h8M7 13h10M7 17h6" stroke="white" stroke-width="1.8" stroke-linecap="round"/>
        <circle cx="20" cy="18" r="4.5" stroke="white" stroke-width="1.5"/>
        <path d="M23.5 21.5l2.5 2.5" stroke="white" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
      <span class="logo-text">Reading Concierge</span>
    </div>
    <!-- 右：用户Chip + 暗色模式 -->
    <div class="topbar-actions">
      <div class="user-chip" id="userChip">
        <span class="avatar" id="avatarInitial">U</span>
        <span id="currentUserId">loading...</span>
      </div>
      <button class="theme-btn" data-theme-toggle aria-label="切换主题"></button>
    </div>
  </header>

  <div class="main">
    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar">
      <!-- Phase 3 填充内容 -->
    </aside>

    <!-- 主内容区（保留原有内容） -->
    <main class="content" id="mainContent">
      <!-- 原有业务内容迁移至此 -->
    </main>
  </div>
</div>
```

### Phase 2 验收检查
- [ ] TopBar sticky，滚动时有 blur 效果
- [ ] Sidebar 280px 固定，主内容区自适应
- [ ] 900px 以下折叠为上下布局
- [ ] 原有功能未受影响

---

## Phase 3 — Sidebar 用户画像组件

**目标**：填充 Sidebar 三个区块，数据来自后端 `GET /api/profile`。

### 任务 3.1 — Sidebar HTML 结构

在 `<aside class="sidebar">` 内填充：

```html
<!-- 区块一：用户设置 -->
<div class="sidebar-section">
  <div class="sidebar-label">用户设置</div>
  <label class="field-label">User ID</label>
  <input type="text" id="userIdInput" class="input-field" placeholder="输入 User ID">
  <label class="field-label">推荐场景</label>
  <select id="scenarioSelect" class="input-field">
    <option value="cold">Cold Start（新用户）</option>
    <option value="warm">Warm Start（有历史）</option>
    <option value="explore">Exploration（高探索）</option>
  </select>
</div>

<div class="sidebar-divider"></div>

<!-- 区块二：用户画像 -->
<div class="sidebar-section">
  <div class="sidebar-label">用户画像（RPA 实时）</div>
  <span id="profileStatusBadge" class="badge badge--warm">Warm User</span>
  <div class="stats-card">
    <div class="stats-row">
      <div class="stat-item">
        <div class="stat-value" id="statEventCount">—</div>
        <div class="stat-label">行为事件</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-value" id="statConfidence">—</div>
        <div class="stat-label">置信度</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-value" id="statSessions">—</div>
        <div class="stat-label">会话数</div>
      </div>
    </div>
  </div>
  <div class="sidebar-sublabel">偏好类型分布</div>
  <div id="profileBarsContainer" class="profile-bars">
    <!-- 由 JS 动态渲染 -->
  </div>
</div>

<div class="sidebar-divider"></div>

<!-- 区块三：RDA 仲裁臂记录 -->
<div class="sidebar-section">
  <div class="sidebar-label">RDA 仲裁臂记录</div>
  <div id="armBarsContainer" class="arm-bars">
    <!-- 由 JS 动态渲染 -->
  </div>
  <p class="sidebar-hint">avg_reward 随反馈实时更新，决定下次仲裁策略</p>
</div>
```

### 任务 3.2 — Sidebar 组件样式（追加到 `styles/components.css`）

```css
/* ─── Sidebar 通用 ─── */
.sidebar-section { display: flex; flex-direction: column; gap: var(--space-3); }
.sidebar-label {
  font-size: var(--text-xs); font-weight: 600;
  letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--color-text-faint);
}
.sidebar-sublabel { font-size: var(--text-xs); font-weight: 600; color: var(--color-text-muted); margin-top: var(--space-1); }
.sidebar-divider { height: 1px; background: var(--color-divider); }
.sidebar-hint { font-size: var(--text-xs); color: var(--color-text-faint); line-height: 1.5; }
.field-label { font-size: var(--text-xs); color: var(--color-text-muted); }

/* ─── Input / Select ─── */
.input-field {
  width: 100%; padding: var(--space-2) var(--space-3);
  background: var(--color-bg); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); font-size: var(--text-sm); outline: none;
}
.input-field:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px color-mix(in oklch, var(--color-primary) 15%, transparent);
}
select.input-field {
  appearance: none; cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%237a7974' stroke-width='2.5'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 10px center;
  padding-right: var(--space-8);
}

/* ─── Badge ─── */
.badge {
  display: inline-flex; align-items: center; gap: var(--space-1);
  padding: 2px var(--space-2); border-radius: var(--radius-full);
  font-size: var(--text-xs); font-weight: 500;
}
.badge--warm { background: var(--color-success-highlight); color: var(--color-success); }
.badge--cold { background: var(--color-warning-highlight); color: var(--color-warning); }

/* ─── Stats Card ─── */
.stats-card {
  background: var(--color-bg); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); padding: var(--space-4);
}
.stats-row { display: flex; justify-content: space-between; align-items: center; }
.stat-item { text-align: center; }
.stat-value {
  font-size: var(--text-lg); font-weight: 600;
  color: var(--color-primary); line-height: 1;
  font-variant-numeric: tabular-nums;
}
.stat-label { font-size: var(--text-xs); color: var(--color-text-muted); margin-top: 2px; }
.stat-divider { width: 1px; height: 36px; background: var(--color-divider); }

/* ─── Profile Bars ─── */
.profile-bars { display: flex; flex-direction: column; gap: var(--space-2); }
.profile-bar-row { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-xs); }
.profile-bar-label { width: 56px; color: var(--color-text-muted); flex-shrink: 0; }
.profile-bar-track {
  flex: 1; height: 6px;
  background: var(--color-surface-offset); border-radius: var(--radius-full); overflow: hidden;
}
.profile-bar-fill {
  height: 100%; border-radius: var(--radius-full);
  background: var(--color-primary);
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.profile-bar-val { width: 28px; text-align: right; color: var(--color-text-faint); font-variant-numeric: tabular-nums; }

/* ─── Arm Bars ─── */
.arm-bars { display: flex; flex-direction: column; gap: var(--space-2); }
.arm-row { display: flex; align-items: center; gap: var(--space-2); }
.arm-label { font-size: var(--text-xs); color: var(--color-text-muted); width: 88px; flex-shrink: 0; }
.arm-track {
  flex: 1; height: 8px;
  background: var(--color-surface-offset); border-radius: var(--radius-full); overflow: hidden;
}
.arm-fill {
  height: 100%; border-radius: var(--radius-full);
  background: var(--color-primary);
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.arm-val { font-size: var(--text-xs); font-variant-numeric: tabular-nums; color: var(--color-text-faint); width: 36px; text-align: right; }

/* ─── User Chip ─── */
.user-chip {
  display: flex; align-items: center; gap: var(--space-2);
  background: var(--color-surface-offset); border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: var(--space-1) var(--space-3) var(--space-1) var(--space-2);
  font-size: var(--text-xs); color: var(--color-text-muted); cursor: pointer;
  transition: border-color var(--transition), color var(--transition);
}
.user-chip:hover { border-color: var(--color-primary); color: var(--color-primary); }
.user-chip .avatar {
  width: 22px; height: 22px; border-radius: var(--radius-full);
  background: var(--color-primary-highlight); color: var(--color-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 600;
}
.theme-btn {
  width: 32px; height: 32px; border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-text-muted);
  transition: background var(--transition), color var(--transition);
}
.theme-btn:hover { background: var(--color-surface-offset); color: var(--color-text); }
```

### 任务 3.3 — Profile API 调用（`js/profile.js`）

```javascript
// js/profile.js
const API_BASE = window.API_BASE || 'http://localhost:8000';

export async function fetchProfile(userId) {
  const res = await fetch(`${API_BASE}/api/profile?user_id=${encodeURIComponent(userId)}`);
  if (!res.ok) throw new Error(`Profile fetch failed: ${res.status}`);
  return res.json();
}

export function renderProfile(profile) {
  // Stats
  document.getElementById('statEventCount').textContent = profile.event_count ?? '—';
  document.getElementById('statConfidence').textContent =
    profile.confidence != null ? profile.confidence.toFixed(2) : '—';
  document.getElementById('statSessions').textContent = profile.session_count ?? '—';

  // Badge
  const badge = document.getElementById('profileStatusBadge');
  badge.className = 'badge badge--' + (profile.status === 'cold' ? 'cold' : 'warm');
  badge.textContent = profile.status === 'cold' ? '⚠ Cold Start' : '✓ Warm User';

  // TopBar user chip
  const userId = profile.user_id || '';
  document.getElementById('currentUserId').textContent = userId;
  document.getElementById('avatarInitial').textContent = userId[0]?.toUpperCase() || 'U';

  // Preference bars
  const container = document.getElementById('profileBarsContainer');
  const prefs = profile.preferences || {};
  container.innerHTML = Object.entries(prefs)
    .sort((a, b) => b[1] - a[1])
    .map(([genre, score]) => `
      <div class="profile-bar-row">
        <div class="profile-bar-label">${genre}</div>
        <div class="profile-bar-track">
          <div class="profile-bar-fill" style="width:${(score * 100).toFixed(1)}%"></div>
        </div>
        <div class="profile-bar-val">${score.toFixed(2)}</div>
      </div>`).join('');

  // RDA arm bars
  const armContainer = document.getElementById('armBarsContainer');
  const arms = profile.rda_arms || [];
  armContainer.innerHTML = arms.map(arm => `
    <div class="arm-row">
      <div class="arm-label">${arm.name}</div>
      <div class="arm-track">
        <div class="arm-fill" id="arm_${arm.name.replace(/\s+/g,'_')}"
          style="width:${Math.min(100, arm.avg_reward * 100).toFixed(1)}%"></div>
      </div>
      <div class="arm-val" id="armv_${arm.name.replace(/\s+/g,'_')}">${arm.avg_reward.toFixed(2)}</div>
    </div>`).join('');
}

export function updateArmBar(armName, newAvgReward) {
  const key = armName.replace(/\s+/g, '_');
  const fill = document.getElementById('arm_' + key);
  const val = document.getElementById('armv_' + key);
  if (fill) fill.style.width = Math.min(100, newAvgReward * 100).toFixed(1) + '%';
  if (val) val.textContent = newAvgReward.toFixed(2);
}
```

### Phase 3 验收检查
- [ ] 页面加载时自动调用 `GET /api/profile` 填充 Sidebar
- [ ] Preference bars 宽度与数值一致
- [ ] RDA arm bars 正确显示
- [ ] Cold/Warm badge 根据 profile.status 正确切换

---

## Phase 4 — 查询、PipelineTrace、结果渲染

**目标**：实现查询流程（含 SSE 流式管道追踪）和推荐结果渲染。

### 任务 4.1 — QueryCard HTML

在 `.content` 顶部插入：
```html
<div class="query-card" id="queryCard">
  <div class="query-input-wrap">
    <div class="query-label">自然语言查询</div>
    <input type="text" id="queryInput" class="query-input"
      placeholder="例：推荐一些关于社会议题的科幻小说">
  </div>
  <div class="query-footer">
    <div class="scenario-chips" id="scenarioChips">
      <button class="chip active" data-scenario="cold">Cold</button>
      <button class="chip" data-scenario="warm">Warm</button>
      <button class="chip" data-scenario="explore">Explore</button>
    </div>
    <button class="btn-primary" id="searchBtn" onclick="runRecommendation()">
      获取推荐
    </button>
  </div>
</div>
```

### 任务 4.2 — PipelineTrace HTML

在 QueryCard 下方插入（默认 `display:none`）：
```html
<div class="pipeline-trace" id="pipelineTrace" style="display:none;" aria-live="polite">
  <div class="pipeline-header">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
    协商管道执行过程
  </div>
  <div id="pipelineSteps">
    <!-- 5 steps: RC / RPA / BCA / RDA / Engine -->
    <!-- 由 js/pipeline.js 动态渲染 -->
  </div>
</div>
```

### 任务 4.3 — `js/pipeline.js`

```javascript
// js/pipeline.js
export const STEP_DEFS = [
  { key: 'RC',     name: 'Reading Concierge — 意图解析',              abbr: 'RC' },
  { key: 'RPA',    name: 'Reader Profile Agent — 生成提案 A',          abbr: 'RPA' },
  { key: 'BCA',    name: 'Book Content Agent — 生成提案 B',            abbr: 'BCA' },
  { key: 'RDA',    name: 'Recommendation Decision Agent — UCB 仲裁',   abbr: 'RDA' },
  { key: 'Engine', name: 'Recommendation Engine — 召回+排序+解释',      abbr: 'ENG' },
];

export function initPipeline() {
  const container = document.getElementById('pipelineSteps');
  container.innerHTML = STEP_DEFS.map((s, i) => `
    <div class="pipeline-step" id="ps_${s.key}">
      <div class="step-icon" id="pi_${s.key}">${s.abbr}</div>
      <div class="step-body">
        <div class="step-name">${s.name}</div>
        <div class="step-detail" id="pd_${s.key}">等待执行…</div>
      </div>
      <div class="step-badge" id="pb_${s.key}">等待</div>
    </div>`).join('');
}

export function setStepRunning(key, detail) {
  const step = document.getElementById('ps_' + key);
  const icon = document.getElementById('pi_' + key);
  const badge = document.getElementById('pb_' + key);
  const detailEl = document.getElementById('pd_' + key);
  step?.classList.add('active');
  icon?.classList.add('active', 'spinning');
  if (badge) { badge.textContent = '执行中'; badge.className = 'step-badge highlight'; }
  if (detailEl && detail) detailEl.textContent = detail;
}

export function setStepDone(key, detail) {
  const step = document.getElementById('ps_' + key);
  const icon = document.getElementById('pi_' + key);
  const badge = document.getElementById('pb_' + key);
  const detailEl = document.getElementById('pd_' + key);
  icon?.classList.remove('spinning', 'active');
  icon?.classList.add('done');
  if (icon) icon.innerHTML = '✓';
  if (badge) { badge.textContent = detail || '完成'; badge.className = 'step-badge'; }
  step?.classList.remove('active');
  step?.classList.add('done');
}
```

### 任务 4.4 — `js/api.js`（SSE 推荐接口）

```javascript
// js/api.js
const API_BASE = window.API_BASE || 'http://localhost:8000';

/**
 * 调用推荐接口（SSE 流式）
 * onStep(step: string, data: object) — 每个 Agent 完成时回调
 * onResults(results: array) — 最终推荐结果回调
 * onError(err: Error) — 错误回调
 */
export function streamRecommendation({ userId, query, scenario, onStep, onResults, onError }) {
  const url = `${API_BASE}/api/recommend/stream?` +
    new URLSearchParams({ user_id: userId, query, scenario });
  const source = new EventSource(url);

  source.addEventListener('pipeline_step', (e) => {
    try { onStep(JSON.parse(e.data)); } catch {}
  });

  source.addEventListener('results', (e) => {
    try {
      onResults(JSON.parse(e.data));
      source.close();
    } catch {}
  });

  source.addEventListener('error', (e) => {
    source.close();
    onError(new Error('SSE connection error'));
  });

  return () => source.close(); // 返回取消函数
}

/**
 * 降级方案：如果后端不支持 SSE，使用 POST
 */
export async function fetchRecommendation({ userId, query, scenario }) {
  const res = await fetch(`${API_BASE}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, query, scenario }),
  });
  if (!res.ok) throw new Error(`Recommend failed: ${res.status}`);
  return res.json();
}

export async function postFeedback({ userId, sessionId, bookId, reward, rank }) {
  const res = await fetch(`${API_BASE}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, session_id: sessionId, book_id: bookId, reward, rank }),
  });
  if (!res.ok) throw new Error(`Feedback failed: ${res.status}`);
  return res.json();
}
```

### 任务 4.5 — ResultCard HTML（由 JS 动态渲染）

```javascript
// js/results.js — renderResultCard(book, index)
export function renderResultCard(book, index) {
  const FEEDBACK_OPTS = [
    { emoji: '📖', reward: 1.0,  label: '读完 / 5星' },
    { emoji: '👍', reward: 0.8,  label: '推荐 / 4星' },
    { emoji: '👀', reward: 0.3,  label: '点击查看' },
    { emoji: '😐', reward: 0.1,  label: '随便看看' },
    { emoji: '👎', reward: -0.5, label: '跳过' },
    { emoji: '❌', reward: -0.8, label: '不感兴趣' },
  ];

  return `
    <div class="result-card" id="rc_${book.book_id}">
      <div class="result-header">
        <div class="rank-badge">${index + 1}</div>
        <div class="result-meta">
          <div class="result-title">${book.title}</div>
          <div class="result-author">${book.author}</div>
          <div class="result-scores">
            <span class="score-tag score-tag--match">匹配度 ${book.match_score?.toFixed(2)}</span>
            <span class="score-tag score-tag--novelty">新颖度 ${book.novelty_score?.toFixed(2)}</span>
            ${book.recall_cf ? '<span class="score-tag score-tag--cf">CF 召回</span>' : ''}
          </div>
        </div>
      </div>
      <div class="result-rationale">"${book.rationale}"</div>
      <div class="feedback-panel">
        <div class="feedback-label">这本书推荐得怎么样？</div>
        <div class="feedback-right">
          <span class="reward-flash" id="rf_${book.book_id}"></span>
          <div class="feedback-actions">
            ${FEEDBACK_OPTS.map(f => `
              <button class="feedback-btn"
                id="fb_${book.book_id}_${f.reward}"
                data-book-id="${book.book_id}"
                data-reward="${f.reward}"
                data-rank="${index}"
                aria-label="${f.label}（reward=${f.reward > 0 ? '+' : ''}${f.reward}）">
                ${f.emoji}
                <span class="feedback-tooltip">${f.label}<br>r=${f.reward > 0 ? '+' : ''}${f.reward}</span>
              </button>`).join('')}
          </div>
        </div>
      </div>
    </div>`;
}
```

### Phase 4 验收检查
- [ ] 点击「获取推荐」后 PipelineTrace 出现，逐步动画
- [ ] SSE 事件正确驱动每个 step 的 running → done 状态
- [ ] 结果卡片正确渲染（书名、分数、召回标记、理由）
- [ ] 无 SSE 时可降级到 POST + 模拟动画

---

## Phase 5 — 反馈闭环回流

**目标**：反馈按钮触发 API → 回流更新 Sidebar + FeedbackSummary。

### 任务 5.1 — `js/feedback.js`

```javascript
// js/feedback.js
import { postFeedback } from './api.js';
import { updateArmBar } from './profile.js';
import { showToast } from './ui.js';

export function initFeedbackHandlers(state) {
  document.getElementById('resultsArea').addEventListener('click', async (e) => {
    const btn = e.target.closest('.feedback-btn');
    if (!btn) return;

    const { bookId, reward, rank } = btn.dataset;
    const rewardF = parseFloat(reward);

    // 视觉：标记选中
    const card = document.getElementById('rc_' + bookId);
    card?.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('selected', 'selected--neg'));
    btn.classList.add(rewardF < 0 ? 'selected--neg' : 'selected');

    // Reward flash
    const flash = document.getElementById('rf_' + bookId);
    if (flash) {
      flash.textContent = (rewardF > 0 ? '+' : '') + rewardF.toFixed(1);
      flash.className = 'reward-flash ' + (rewardF > 0 ? 'reward-flash--pos' : 'reward-flash--neg');
    }

    try {
      const resp = await postFeedback({
        userId: state.userId,
        sessionId: state.sessionId,
        bookId, reward: rewardF,
        rank: parseInt(rank),
      });

      // 1. 更新 RDA arm bar
      if (resp.rda_arm_updated) {
        const { arm_name, new_avg_reward } = resp.rda_arm_updated;
        updateArmBar(arm_name, new_avg_reward);
      }

      // 2. 画像更新
      if (resp.profile_updated && resp.new_profile) {
        import('./profile.js').then(m => m.renderProfile(resp.new_profile));
        showToast('✅ 用户画像已增量更新（FA → RPA）', 'success');
      }

      // 3. CF 重训
      if (resp.cf_retrain_triggered) {
        showToast('🔄 CF 重训已触发（FA → Engine Agent）', 'warning');
      }

      // 4. 更新 FeedbackSummary
      updateFeedbackSummary(state, bookId, rewardF, resp);

      // 5. 全部提交检查
      state.feedbackGiven[bookId] = rewardF;
      if (Object.keys(state.feedbackGiven).length === state.resultCount) {
        setTimeout(() => showToast('📡 本次会话反馈已全部提交至 RDA', 'default'), 400);
      }

    } catch (err) {
      showToast('⚠ 反馈提交失败，请重试', 'error');
      console.error('Feedback error:', err);
    }
  });
}

function updateFeedbackSummary(state, bookId, reward, resp) {
  // 更新 RDA session reward
  state.rdaRewardSum += reward;
  const rdaEl = document.getElementById('tvRDA');
  if (rdaEl) rdaEl.textContent = state.rdaRewardSum.toFixed(1);

  // 更新 profile progress
  const eventCount = resp.new_profile?.event_count ?? state.eventCount;
  const profileThreshold = state.thresholds.profileUpdate;
  const profPct = Math.min(100, (eventCount / profileThreshold) * 100);
  const tbProfile = document.getElementById('tbProfile');
  if (tbProfile) tbProfile.style.width = profPct + '%';
  const tvProfile = document.getElementById('tvProfile');
  if (tvProfile) {
    if (eventCount >= profileThreshold) {
      tvProfile.innerHTML = `<span class="trigger-fired">✓ 已触发</span> ${eventCount} / ${profileThreshold}`;
    } else {
      tvProfile.textContent = `${eventCount} / ${profileThreshold}`;
    }
  }

  // 更新 CF retrain progress
  if (resp.cf_retrain_triggered) {
    const tbCF = document.getElementById('tbCF');
    if (tbCF) tbCF.style.width = '100%';
  }
}
```

### 任务 5.2 — FeedbackSummary HTML

在 ResultsList 下方插入（初始 `display:none`）：
```html
<div class="feedback-summary" id="feedbackSummary" style="display:none;">
  <div class="summary-header">
    <div class="summary-title">📡 反馈闭环状态</div>
    <div class="summary-hint">你的评分会实时更新 RDA 臂记录和用户画像</div>
  </div>
  <div class="trigger-items">
    <div class="trigger-item">
      <div class="trigger-name">RDA reward 累计（本次会话）</div>
      <div class="trigger-progress">
        <div class="trigger-bar-track">
          <div class="trigger-bar-fill" id="tbRDA" style="width:0%;background:var(--color-primary)"></div>
        </div>
        <div class="trigger-val" id="tvRDA">0</div>
      </div>
    </div>
    <div class="trigger-item">
      <div class="trigger-name">画像更新阈值</div>
      <div class="trigger-progress">
        <div class="trigger-bar-track">
          <div class="trigger-bar-fill" id="tbProfile" style="width:0%;background:var(--color-warning)"></div>
        </div>
        <div class="trigger-val" id="tvProfile">— / —</div>
      </div>
    </div>
    <div class="trigger-item">
      <div class="trigger-name">CF 重训阈值</div>
      <div class="trigger-progress">
        <div class="trigger-bar-track">
          <div class="trigger-bar-fill" id="tbCF" style="width:0%;background:var(--color-gold)"></div>
        </div>
        <div class="trigger-val" id="tvCF">— / —</div>
      </div>
    </div>
  </div>
</div>
```

### 任务 5.3 — Toast 系统（`js/ui.js`）

```javascript
// js/ui.js
export function showToast(message, type = 'default') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.setAttribute('role', 'status');
    container.setAttribute('aria-live', 'polite');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

export function showSkeleton(containerId, count = 3) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = Array(count).fill(`
    <div class="result-card" style="padding:var(--space-5)">
      <div class="skeleton" style="height:20px;width:60%;margin-bottom:var(--space-3)"></div>
      <div class="skeleton" style="height:14px;width:40%;margin-bottom:var(--space-4)"></div>
      <div class="skeleton" style="height:40px;width:100%"></div>
    </div>`).join('');
}
```

### Phase 5 验收检查
- [ ] 点击任意反馈按钮后，POST /api/feedback 成功
- [ ] RDA arm bar 在 Sidebar 中动画更新
- [ ] profile_updated=true 时 Toast 出现 + Sidebar 画像刷新
- [ ] FeedbackSummary 三进度条随反馈变化
- [ ] 全部书目反馈后出现"会话完成"Toast

---

## Phase 6 — 动效与无障碍收尾

**目标**：补全动画细节，通过无障碍检查。

### 任务 6.1 — `styles/animations.css`

```css
/* Pipeline step spinning */
@keyframes spin { to { transform: rotate(360deg); } }
.step-icon.spinning { animation: spin 0.8s linear infinite; }

/* Skeleton shimmer */
@keyframes shimmer {
  0%   { background-position: -200% 0; }
  100% { background-position:  200% 0; }
}
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-surface-offset) 25%,
    var(--color-divider) 50%,
    var(--color-surface-offset) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

/* Toast slide up */
@keyframes slideUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.toast { animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1); }

/* Result card fade in */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}
.result-card { animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) both; }
.result-card:nth-child(2) { animation-delay: 0.08s; }
.result-card:nth-child(3) { animation-delay: 0.16s; }

/* Reward flash fade */
.reward-flash { transition: opacity 0.3s; }
.reward-flash--pos { color: var(--color-success); }
.reward-flash--neg { color: var(--color-error); }
```

### 任务 6.2 — 无障碍 checklist

为以下元素添加正确属性：
- `<button class="feedback-btn">` → `aria-label="[label]（reward=[r]）"`
- PipelineTrace 容器 → `aria-live="polite"`
- Toast 容器 → `role="status" aria-live="polite"`
- 所有图标按钮 → `aria-label` 描述功能
- `.input-field` → 对应 `<label for="...">` 关联

### Phase 6 验收检查
- [ ] skeleton shimmer 动画正常
- [ ] result card 依次 fade in
- [ ] Pipeline step icon 旋转 → 变 ✓
- [ ] Toast 右下角 slide up，3.5s 后消失
- [ ] 键盘 Tab 可顺序访问所有交互元素
- [ ] 无 WCAG 颜色对比度不足警告

---

## 最终验收（所有 Phase 完成后）

```
□ GET /api/profile  → Sidebar 画像正确显示
□ POST /api/recommend → SSE 动画 → 结果卡片渲染
□ POST /api/feedback → RDA arm 更新 + Toast 通知
□ 暗色模式切换正常，LocalStorage 持久化
□ 900px 以下响应式正常
□ prefers-reduced-motion 时无动画闪烁
□ 控制台无报错，network tab 无 4xx/5xx（后端正常时）
```
