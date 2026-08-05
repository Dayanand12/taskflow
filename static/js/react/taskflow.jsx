// TaskFlow — React components (no-build, compiled in-browser via Babel standalone).
//
// Migration is incremental, view by view. This file currently owns:
//   - Dashboard (#dashboard)
//   - List view (#view-list)
// Every other view (Today/Next7/Kanban/Calendar/Reminders/Workflows/Notes,
// the detail panel, and all modals) is still rendered by the legacy inline
// script in task_manager.html and is untouched by this file.
//
// Bridge pattern: these components are pure functions of the app's existing
// global state (allTasks, currentFilter, etc). They don't own that state —
// the legacy code still mutates it and still decides *when* to re-render
// (via renderDashboard()/renderList()/renderAll()), so every existing call
// site keeps working unchanged. React is only responsible for turning a
// snapshot of that state into DOM here, instead of hand-built innerHTML.

function DueBadge({ t, today }) {
  if (!t.due_date || ['completed', 'cancelled'].includes(t.status)) return null;
  const timeStr = t.due_time ? ` ${fmtTime12(t.due_time)}` : '';
  let cls = 'due-n', lbl = fmtDue(t.due_date) + timeStr;
  if (t.due_date < today) { cls = 'due-o'; lbl = '⚠ Overdue'; }
  else if (t.due_date === today) { cls = 'due-t'; lbl = '📅 Today' + timeStr; }
  return <span className={`due-chip ${cls}`}>{lbl}</span>;
}

function PomoWidget({ id }) {
  // Pure DOM-id-driven timer (see togglePomoWidget/_updatePomoDom in the legacy
  // script) — it never re-renders through React, so this is static markup only.
  return (
    <div className="pomo-widget" id={`pw-${id}`} style={{ display: 'none' }} onClick={e => e.stopPropagation()}>
      <div className="pomo-dur-row">
        <button className="pomo-dur-btn sel" data-mins="25" onClick={e => setPomoMode(id, e.currentTarget)}>🍅 Pomodoro</button>
        <button className="pomo-dur-btn" data-mins="5" onClick={e => setPomoMode(id, e.currentTarget)}>⚡ Short</button>
        <button className="pomo-dur-btn" data-mins="15" onClick={e => setPomoMode(id, e.currentTarget)}>☕ Long</button>
      </div>
      <div className="pomo-main">
        <div className="pomo-display" id={`pd-${id}`}>25:00</div>
        <div className="pomo-progress-wrap">
          <div className="pomo-progress-track"><div className="pomo-progress-fill" id={`ppf-${id}`} style={{ width: '100%' }}></div></div>
          <div className="pomo-ctrl-row">
            <button className="pomo-play-btn" id={`ppb-${id}`} onClick={() => togglePomoTimer(id)}>▶</button>
            <button className="pomo-reset-btn" onClick={() => resetPomoTimer(id)}>↺</button>
            <span className="pomo-label" id={`pl-${id}`}>Ready</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function TaskCard({ t, today, selectMode, selected, isActivePanel, hideStep, showPomo, clickFn }) {
  const isDone = ['completed', 'cancelled'].includes(t.status);
  const ttype = t.task_type || 'general';
  const tt = TC[ttype] || TC.general;
  const recurLbl = { daily: 'Daily', weekdays: 'Weekdays', weekly: 'Weekly', biweekly: '2-week', monthly: 'Monthly' };
  const pomoOn = showPomo && pomos[t.id]?.running;
  const onOpen = clickFn || openPanel;

  const card = (
    <div
      className={`task-card prio-${t.priority} ${selected ? 'selected' : ''} ${isActivePanel ? 'active-panel' : ''}`}
      id={`card-${t.id}`}
      onClick={() => onOpen(t.id)}
    >
      <div className="check-col" onClick={e => e.stopPropagation()}>
        <div className={`quick-check ${isDone ? 'done' : ''}`} onClick={() => quickComplete(t.id)} title={isDone ? 'Reopen' : 'Complete'}></div>
        <div className={`bulk-check ${selectMode ? 'show' : ''} ${selected ? 'chk' : ''}`} onClick={() => toggleSel(t.id)}></div>
      </div>
      <span className={`pdot p-${t.priority || 'medium'}`} onClick={e => { e.stopPropagation(); cyclePriority(t.id); }} title="Click to cycle priority"></span>
      <div className="task-body">
        <div className={`task-title ${isDone ? 'done-t' : ''}`}>{t.title}</div>
        {t.description ? <div className="task-desc">{t.description}</div> : null}
        <div className="task-foot">
          {t.project ? <span className="task-project">📁 {t.project}</span> : null}
          {t.step && !hideStep ? (
            <span className="task-step" onClick={e => { e.stopPropagation(); openTaskPage(t.step.workflow_id); }} title={t.step.workflow_title}>
              📍 {t.step.title}
            </span>
          ) : null}
          {t.is_blocked && !isDone ? (
            <span
              className="blocked-badge"
              title={`Blocked by: ${(t.depends_on || []).filter(d => !['completed', 'cancelled'].includes(d.status)).map(d => d.title).join(', ')}`}
            >
              🔒 Blocked
            </span>
          ) : null}
          {ttype !== 'general' ? (
            <span className="type-badge" style={{ background: tt.color + '22', color: tt.color, border: `1px solid ${tt.color}44` }}>
              {tt.icon} {tt.label}
            </span>
          ) : null}
          {t.estimated_minutes ? <span className="est-badge">⏳ {fmtMin(t.estimated_minutes)}</span> : null}
          {(t.time_total || t.active_timer_since) ? (
            <span className={`est-badge ${t.active_timer_since ? 'time-run' : ''}`}>⏱ {t.active_timer_since ? 'live' : fmtDur(t.time_total)}</span>
          ) : null}
          {t.recurrence && t.recurrence !== 'none' ? (
            <span className="est-badge" title={`Repeats ${t.recurrence}`} style={{ color: '#a78bfa' }}>↻ {recurLbl[t.recurrence] || t.recurrence}</span>
          ) : null}
          {(t.tags || []).map(tg => (
            <span className="tag-chip" style={{ background: tg.color }} key={tg.id}><span className="tc-dot"></span>{tg.name}</span>
          ))}
        </div>
        {t.subtask_total ? (
          <React.Fragment>
            <div className="sub-bar">
              <div className="sub-track"><div className="sub-fill" style={{ width: `${Math.round(t.subtask_done / t.subtask_total * 100)}%` }}></div></div>
              <span className="sub-lbl">{t.subtask_done}/{t.subtask_total}</span>
            </div>
            {(t.subtask_preview || []).length ? (
              <div className="sub-preview">
                {t.subtask_preview.map((s, i) => (
                  <span className="sub-preview-item" key={i}><span className="sub-preview-box"></span><span className="sub-preview-text">{s}</span></span>
                ))}
              </div>
            ) : null}
          </React.Fragment>
        ) : null}
      </div>
      <div className="task-right" onClick={e => e.stopPropagation()}>
        <span className={`sb sb-${t.status}`} onClick={e => showStatusMenu(e, t.id)}><span className="sdot"></span>{SL[t.status]}</span>
        <DueBadge t={t} today={today} />
        <div className="task-actions">
          {showPomo ? (
            <button className={`act-btn ${pomoOn ? 'pomo-act-on' : ''}`} id={`pomo-open-${t.id}`} onClick={e => { e.stopPropagation(); togglePomoWidget(t.id); }} title="Pomodoro timer">🍅</button>
          ) : null}
          <button className={`act-btn bell ${t.reminder ? 'has-rem' : ''}`} onClick={() => openRemModal(t.id)} title="Reminder">{t.reminder ? '🔔' : '🔕'}</button>
          <button className="act-btn del" onClick={() => deleteTask(t.id)}>✕</button>
        </div>
      </div>
    </div>
  );

  if (!showPomo) return card;
  return (
    <div className="card-pomo-wrap">
      {card}
      <PomoWidget id={t.id} />
    </div>
  );
}

function ListView({ tasks, today, groupByProject, selectMode, selectedIds, panelTaskId }) {
  const [doneOpen, setDoneOpen] = React.useState(false);
  const [collapsedGroups, setCollapsedGroups] = React.useState(() => new Set());

  if (!tasks.length) return <div className="empty-state">No tasks found.</div>;

  const active = tasks.filter(t => !['completed', 'cancelled'].includes(t.status));
  const done = tasks.filter(t => ['completed', 'cancelled'].includes(t.status));
  const cardProps = t => ({ t, today, selectMode, selected: selectedIds.has(t.id), isActivePanel: panelTaskId === t.id });

  let activeContent;
  if (groupByProject) {
    const groups = new Map();
    active.forEach(t => { const k = t.project || ''; if (!groups.has(k)) groups.set(k, []); groups.get(k).push(t); });
    const sorted = [...[...groups.keys()].filter(k => k).sort(), ...[...groups.keys()].filter(k => !k)];
    activeContent = sorted.map(k => {
      const gTasks = groups.get(k);
      const label = k || 'No Project';
      const isCollapsed = collapsedGroups.has(k);
      return (
        <div className="proj-group" key={k || '__none__'}>
          <div
            className="proj-group-hdr"
            onClick={() => setCollapsedGroups(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; })}
          >
            <span className={`proj-group-chevron ${isCollapsed ? '' : 'open'}`}>▶</span>
            <span className="proj-group-label">📁 {label}</span>
            <span className="proj-group-cnt">{gTasks.length}</span>
          </div>
          <div className={`proj-group-body ${isCollapsed ? 'collapsed' : ''}`}>
            {gTasks.map(t => <TaskCard key={t.id} {...cardProps(t)} />)}
          </div>
        </div>
      );
    });
  } else {
    activeContent = (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {active.map(t => <TaskCard key={t.id} {...cardProps(t)} />)}
      </div>
    );
  }

  return (
    <React.Fragment>
      {activeContent}
      {done.length ? (
        <React.Fragment>
          <div className="done-section-hdr" onClick={() => setDoneOpen(o => !o)}>
            <span className={`done-chevron ${doneOpen ? 'open' : ''}`}>▶</span>
            <span>Completed &amp; Cancelled ({done.length})</span>
          </div>
          <div className={`done-list ${doneOpen ? '' : 'collapsed'}`} id="done-list-inner">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {done.map(t => <TaskCard key={t.id} {...cardProps(t)} />)}
            </div>
          </div>
        </React.Fragment>
      ) : null}
    </React.Fragment>
  );
}

function MeetingCard({ m }) {
  const isDone = ['completed', 'cancelled'].includes(m.status);
  const timeStr = m.time ? `🕐 ${fmtTime12(m.time)}` : '';
  const durStr = m.duration_minutes ? `⏱ ${fmtMin(m.duration_minutes)}` : '';
  const recurLbl = { daily: 'Daily', weekdays: 'Weekdays', weekly: 'Weekly', biweekly: '2-week', monthly: 'Monthly' };

  return (
    <div className="task-card meeting-card prio-medium" id={`mtgcard-${m.id}`} onClick={() => openMeetingModal(m.id)}>
      <div className="check-col" onClick={e => e.stopPropagation()}>
        <div className="mtg-icon">{isDone ? '✓' : '📅'}</div>
      </div>
      <div className="task-body">
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span className={`task-title ${isDone ? 'done-t' : ''}`}>{m.title}</span>
          <span className="mtg-type-pill">Meeting</span>
        </div>
        <div className="task-foot">
          {timeStr ? <span className="est-badge">{timeStr}</span> : null}
          {durStr ? <span className="est-badge">{durStr}</span> : null}
          {m.location ? <span className="est-badge">📍 {m.location}</span> : null}
          {m.recurrence && m.recurrence !== 'none' ? <span className="est-badge" style={{ color: '#a78bfa' }}>↻ {recurLbl[m.recurrence] || m.recurrence}</span> : null}
          {m._virtual ? <span className="est-badge" style={{ color: '#f59e0b', border: '1px solid #f59e0b33' }}>projected</span> : null}
        </div>
        {(m.point_preview || []).length ? (
          <div className="sub-preview">
            {m.point_preview.map((p, i) => (
              <span className="sub-preview-item" key={i}><span className="sub-preview-box"></span><span className="sub-preview-text">{p}</span></span>
            ))}
          </div>
        ) : null}
      </div>
      <div className="task-right" onClick={e => e.stopPropagation()}>
        <span className={`sb sb-mtg-${m._virtual ? 'upcoming' : m.status}`}>{m._virtual ? 'upcoming' : m.status}</span>
        {m.point_total ? <span className="est-badge">📋 {m.point_done}/{m.point_total}</span> : null}
        <div className="task-actions">
          <button className="act-btn del" onClick={() => deleteMeeting(m.id)}>✕</button>
        </div>
      </div>
    </div>
  );
}

function Section({ cls, label, count, empty, children }) {
  const hasCount = count !== undefined && count !== null;
  return (
    <React.Fragment>
      <div className={`section-hdr ${cls || ''}`}>
        <span className="section-hdr-title">{label}</span>
        {hasCount ? <span className="section-hdr-cnt">{count}</span> : null}
        <span className="section-hdr-line"></span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginBottom: '6px' }}>
        {children || empty}
      </div>
    </React.Fragment>
  );
}

function TodayView({ allTasks, allMeetings, today }) {
  const overdue = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.due_date && t.due_date < today && !['completed', 'cancelled'].includes(t.status));
  const todayT = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.due_date === today && !['completed', 'cancelled'].includes(t.status));
  const inProc = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.status === 'in_process' && (!t.due_date || t.due_date > today));
  const realTodayMtg = allMeetings.filter(m => m.date === today && !['cancelled'].includes(m.status));
  const virtualTodayMtg = [];
  allMeetings.filter(m => m.recurrence && m.recurrence !== 'none' && !['cancelled', 'completed'].includes(m.status) && m.date !== today).forEach(m => {
    if (getOccurrenceDates(m.date, m.recurrence, today, today).includes(today) && ![...realTodayMtg, ...virtualTodayMtg].some(r => r.title === m.title && r.recurrence === m.recurrence))
      virtualTodayMtg.push({ ...m, _virtual: true, date: today });
  });
  const todayMtg = [...realTodayMtg, ...virtualTodayMtg].sort((a, b) => (a.time || '').localeCompare(b.time || ''));
  const byP = arr => [...arr].sort((a, b) => PO[b.priority] - PO[a.priority]);

  const hasContent = overdue.length || todayT.length || inProc.length || todayMtg.length;

  return (
    <React.Fragment>
      {hasContent ? (
        <React.Fragment>
          {overdue.length ? <Section cls="section-overdue" label="Overdue" count={overdue.length}>{byP(overdue).map(t => <TaskCard key={t.id} t={t} today={today} showPomo />)}</Section> : null}
          {todayT.length ? <Section cls="section-today" label="Today" count={todayT.length}>{byP(todayT).map(t => <TaskCard key={t.id} t={t} today={today} showPomo />)}</Section> : null}
          {inProc.length ? <Section label="In Progress" count={inProc.length}>{byP(inProc).map(t => <TaskCard key={t.id} t={t} today={today} showPomo />)}</Section> : null}
          {todayMtg.length ? <Section label="Meetings Today" count={todayMtg.length}>{todayMtg.map(m => <MeetingCard key={m.id} m={m} />)}</Section> : null}
        </React.Fragment>
      ) : (
        <div className="empty-state" style={{ marginBottom: '12px' }}>No tasks due today — you're all clear! 🎉</div>
      )}
      <div className="quick-add-row">
        <input
          type="text" className="quick-add-inp" id="today-quick-add"
          placeholder="+ Quick add task for today… (Enter to save)"
          onKeyDown={e => { if (e.key === 'Enter') quickAddToday(e); }}
        />
      </div>
    </React.Fragment>
  );
}

function Next7View({ allTasks, today }) {
  const days = [];
  for (let i = 0; i < 7; i++) { const d = new Date(); d.setDate(d.getDate() + i); days.push(d.toISOString().split('T')[0]); }
  const overdue = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.due_date && t.due_date < today && !['completed', 'cancelled'].includes(t.status));
  const noDate = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && !t.due_date && !['completed', 'cancelled'].includes(t.status));

  function dayLabel(ds) {
    const d = new Date(ds + 'T00:00:00');
    if (ds === today) return 'Today';
    const tom = new Date(); tom.setDate(tom.getDate() + 1);
    if (ds === tom.toISOString().split('T')[0]) return 'Tomorrow';
    return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
  }

  const anyContent = overdue.length || days.length || noDate.length;
  if (!anyContent) return <div className="empty-state">No upcoming tasks in the next 7 days</div>;

  return (
    <React.Fragment>
      {overdue.length ? (
        <Section cls="section-overdue" label="Overdue" count={overdue.length}>
          {overdue.map(t => <TaskCard key={t.id} t={t} today={today} />)}
        </Section>
      ) : null}
      {days.map(ds => {
        const realDayTasks = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.due_date === ds && !['completed', 'cancelled'].includes(t.status));
        const virtualDayTasks = [];
        allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.due_date && t.recurrence && t.recurrence !== 'none' && !['completed', 'cancelled'].includes(t.status) && t.due_date !== ds).forEach(t => {
          if (getOccurrenceDates(t.due_date, t.recurrence, ds, ds).includes(ds) && ![...realDayTasks, ...virtualDayTasks].some(r => r.title === t.title && r.recurrence === t.recurrence))
            virtualDayTasks.push({ ...t, _virtual: true, due_date: ds });
        });
        const dayTasks = [...realDayTasks, ...virtualDayTasks];
        const label = dayLabel(ds);
        return (
          <Section key={ds} cls={ds === today ? 'section-today' : ''} label={label} count={dayTasks.length || undefined} empty={<div className="day-empty">No tasks for {label.toLowerCase()}</div>}>
            {dayTasks.length ? dayTasks.map(t => <TaskCard key={t.id} t={t} today={today} />) : null}
          </Section>
        );
      })}
      {noDate.length ? (
        <Section label="No Due Date" count={noDate.length}>
          {noDate.map(t => <TaskCard key={t.id} t={t} today={today} />)}
        </Section>
      ) : null}
    </React.Fragment>
  );
}

function KanbanCard({ t, today }) {
  const due = t.due_date && !['completed', 'cancelled'].includes(t.status) ? (
    <span className={`due-chip ${t.due_date < today ? 'due-o' : t.due_date === today ? 'due-t' : 'due-n'}`} style={{ fontSize: '.6rem' }}>
      {t.due_date < today ? '⚠' : t.due_date === today ? 'Today' : fmtDue(t.due_date)}
    </span>
  ) : null;

  return (
    <div
      className={`kcard kprio-${t.priority}`} draggable="true" data-id={t.id}
      onClick={() => openPanel(t.id)}
      onDragStart={e => kDragStart(e, t.id)} onDragEnd={e => kDragEnd(e)}
    >
      <div style={{ display: 'flex', gap: '6px', alignItems: 'flex-start' }}>
        <span className={`pdot p-${t.priority}`} style={{ marginTop: '3px', flexShrink: 0 }}></span>
        <span className="kcard-title">{t.title}</span>
        {t.recurrence && t.recurrence !== 'none' ? <span className="kcard-sub" style={{ color: '#a78bfa' }}>↻</span> : null}
        {t.is_blocked && !['completed', 'cancelled'].includes(t.status) ? <span className="kcard-sub" style={{ color: '#f59e0b' }} title="Blocked">🔒</span> : null}
      </div>
      {(t.tags || []).length ? (
        <div className="kcard-tags">
          {t.tags.map(tg => <span className="tag-chip" style={{ background: tg.color, fontSize: '.6rem', padding: '2px 5px' }} key={tg.id}>{tg.name}</span>)}
        </div>
      ) : null}
      <div className="kcard-meta">
        {due}
        {t.subtask_total ? <span className="kcard-sub">☑ {t.subtask_done}/{t.subtask_total}</span> : null}
        {t.estimated_minutes ? <span className="kcard-sub">⏳{fmtMin(t.estimated_minutes)}</span> : null}
        {t.step ? <span className="kcard-sub" style={{ color: '#c084fc' }} title={t.step.workflow_title}>📍 {t.step.title}</span> : null}
      </div>
    </div>
  );
}

function KanbanBoard({ allTasks, today }) {
  return (
    <div className="kanban-board">
      {Object.entries(SL).map(([s, label]) => {
        const tasks = [...allTasks.filter(t => t.status === s && t.task_type !== 'workflow' && !t.step_id)].sort((a, b) => PO[b.priority] - PO[a.priority]);
        return (
          <div className="kanban-col" key={s} onDragOver={e => kDragOver(e)} onDrop={e => kDrop(e, s)} onDragLeave={e => kDragLeave(e)}>
            <div className="kcol-hdr">
              <span className="sdot" style={{ background: SC[s], width: '8px', height: '8px', borderRadius: '50%', flexShrink: 0 }}></span>
              <span className="kcol-ttl">{label}</span><span className="kcol-cnt">{tasks.length}</span>
            </div>
            <div className="kcol-body">
              {tasks.map(t => <KanbanCard key={t.id} t={t} today={today} />)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CalendarView({ allTasks, allMeetings, calYear, calMonth, today }) {
  const first = new Date(calYear, calMonth, 1), last = new Date(calYear, calMonth + 1, 0);
  const startDow = (first.getDay() + 6) % 7, daysInMonth = last.getDate();
  const taskMap = {}, mtgMap = {};
  allTasks.filter(t => t.due_date && t.task_type !== 'workflow' && !t.step_id).forEach(t => { if (!taskMap[t.due_date]) taskMap[t.due_date] = []; taskMap[t.due_date].push(t); });
  allMeetings.forEach(m => { if (!mtgMap[m.date]) mtgMap[m.date] = []; mtgMap[m.date].push(m); });
  const monthStart = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-01`;
  const monthEnd = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`;

  // Virtual future occurrences for recurring tasks (active only)
  allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id && t.due_date && t.recurrence && t.recurrence !== 'none' && !['completed', 'cancelled'].includes(t.status)).forEach(t => {
    getOccurrenceDates(t.due_date, t.recurrence, monthStart, monthEnd).forEach(ds => {
      if (ds === t.due_date) return;
      if (!(taskMap[ds] || []).some(r => r.title === t.title && r.recurrence === t.recurrence)) {
        if (!taskMap[ds]) taskMap[ds] = [];
        taskMap[ds].push({ ...t, _virtual: true, due_date: ds });
      }
    });
  });
  // Virtual future occurrences for recurring meetings (active only, not completed/cancelled)
  allMeetings.filter(m => m.recurrence && m.recurrence !== 'none' && !['cancelled', 'completed'].includes(m.status)).forEach(m => {
    getOccurrenceDates(m.date, m.recurrence, monthStart, monthEnd).forEach(ds => {
      if (ds === m.date) return;
      if (!(mtgMap[ds] || []).some(r => r.title === m.title && r.recurrence === m.recurrence)) {
        if (!mtgMap[ds]) mtgMap[ds] = [];
        mtgMap[ds].push({ ...m, _virtual: true, date: ds });
      }
    });
  });

  const monthName = first.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  const total = Math.ceil((startDow + daysInMonth) / 7) * 7;
  const cells = [];
  for (let i = 0; i < total; i++) {
    const dn = i - startDow + 1;
    if (dn < 1 || dn > daysInMonth) {
      cells.push(<div className="cal-day other-m" key={`o${i}`}><div className="cal-day-num">{dn < 1 ? '' : dn}</div></div>);
      continue;
    }
    const ds = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-${String(dn).padStart(2, '0')}`;
    const isT = ds === today;
    const dt = taskMap[ds] || [], dm = mtgMap[ds] || [];
    cells.push(
      <div className={`cal-day ${isT ? 'today-cell' : ''}`} key={ds} onClick={() => openCalDay(ds)}>
        <div className="cal-day-num">
          {dn}
          {Array.from({ length: Math.min(dm.length, 3) }).map((_, i2) => (
            <span className="cal-mtg-dot" key={i2} title={`${dm.length} meeting${dm.length > 1 ? 's' : ''}`}></span>
          ))}
        </div>
        {dt.slice(0, 2).map(t => (
          <span
            className="cal-task-chip" key={t.id}
            style={{ background: SC[t.status], ...(t._virtual ? { opacity: .6, outline: '1px dashed rgba(255,255,255,.4)' } : {}) }}
            onClick={e => { e.stopPropagation(); openCalDay(ds); }}
          >
            {t._virtual ? '↻ ' : ''}{t.title}
          </span>
        ))}
        {(dt.length > 2 || dm.length) ? (
          <div className="cal-more">{dt.length > 2 ? `+${dt.length - 2} tasks` : ''} {dm.length ? `📅${dm.length}` : ''}</div>
        ) : null}
      </div>
    );
  }

  return (
    <React.Fragment>
      <div className="cal-header">
        <button className="cal-nav" onClick={() => calNav(-1)}>‹</button>
        <span className="cal-month-lbl">{monthName}</span>
        <button className="cal-nav" onClick={() => calNav(1)}>›</button>
        <button className="cal-nav" style={{ width: 'auto', padding: '0 9px', fontSize: '.75rem' }} onClick={() => calToday()}>Today</button>
      </div>
      <div className="cal-grid">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(d => <div className="cal-dow" key={d}>{d}</div>)}
        {cells}
      </div>
    </React.Fragment>
  );
}

const REM_TYPE_ICONS = { meeting: '📅', call: '📞', task: '✅', deadline: '⏰', personal: '🏠', general: '🔔' };

function ReminderCard({ r, today }) {
  const nowIso = () => new Date().toISOString().replace('T', ' ').substring(0, 19);
  const now = nowIso();
  const isOver = r.remind_at < now, isToday = r.remind_at.substring(0, 10) === today;
  const cls = isOver ? 'rc-overdue' : isToday ? 'rc-today' : 'rc-upcoming';
  const timeCls = isOver ? 'overdue' : isToday ? 'today' : 'upcoming';
  const icon = r.type === 'standalone' ? (REM_TYPE_ICONS[r.reminder_type] || '🔔') : '📋';

  return (
    <div className={`rem-card ${cls}`}>
      <span className="rem-card-icon">{icon}</span>
      <div className="rem-card-body">
        <div className="rem-card-title">{r.title}</div>
        {r.note ? <div className="rem-card-note">{r.note}</div> : null}
        <div className="rem-card-meta">
          <span className={`rem-time-badge ${timeCls}`}>{isOver ? '⚠ Overdue · ' : ''}{fmtDateTime(r.remind_at)}</span>
          {r.recurrence && r.recurrence !== 'none' ? <span className="rem-recur-badge">↻ {capFirst(r.recurrence)}</span> : null}
          {r.type === 'task' ? <span className="rem-task-link">📋 task</span> : null}
        </div>
      </div>
      <div className="rem-card-actions">
        <button className="rem-edit-btn" onClick={() => (r.type === 'standalone' ? openStandaloneRemModal(r.id) : openPanel(r.task_id))}>✏</button>
        <button
          className="rem-del-btn"
          onClick={e => { e.stopPropagation(); r.type === 'standalone' ? deleteStandaloneReminderById(r.id) : removeTaskReminderById(r.task_id); }}
        >✕</button>
      </div>
    </div>
  );
}

function RemindersView({ allTasks, allStandaloneReminders, today }) {
  const nowIso = () => new Date().toISOString().replace('T', ' ').substring(0, 19);
  const taskRems = allTasks
    .filter(t => t.reminder && !['completed', 'cancelled'].includes(t.status))
    .map(t => ({ ...t.reminder, title: t.title, type: 'task', task_id: t.id }));
  const standaloneRems = allStandaloneReminders.map(r => ({ ...r, type: 'standalone' }));
  const all = [...taskRems, ...standaloneRems].sort((a, b) => a.remind_at.localeCompare(b.remind_at));
  const now = nowIso();
  const overdue = all.filter(r => r.remind_at < now);
  const upcoming = all.filter(r => r.remind_at >= now);

  return (
    <React.Fragment>
      <div className="rem-view-hdr">
        <div className="rem-view-title">🔔 All Reminders</div>
        <button className="hdr-btn primary" onClick={() => openStandaloneRemModal(null)}>+ New Reminder</button>
      </div>
      {overdue.length ? (
        <React.Fragment>
          <div className="rem-section-label">⚠ Overdue ({overdue.length})</div>
          {overdue.map((r, i) => <ReminderCard key={`${r.type}-${r.type === 'standalone' ? r.id : r.task_id}-${i}`} r={r} today={today} />)}
        </React.Fragment>
      ) : null}
      {upcoming.length ? (
        <React.Fragment>
          <div className="rem-section-label">Upcoming ({upcoming.length})</div>
          {upcoming.map((r, i) => <ReminderCard key={`${r.type}-${r.type === 'standalone' ? r.id : r.task_id}-${i}`} r={r} today={today} />)}
        </React.Fragment>
      ) : null}
      {!all.length ? (
        <div className="rem-empty">No reminders set<br /><small>Use "+ New Reminder" to create a meeting, call, or any reminder</small></div>
      ) : null}
    </React.Fragment>
  );
}

function WorkflowsView({ allTasks, today }) {
  const [doneOpen, setDoneOpen] = React.useState(false);
  const workflows = allTasks.filter(t => t.task_type === 'workflow');
  const byP = arr => [...arr].sort((a, b) => PO[b.priority] - PO[a.priority]);
  const active = byP(workflows.filter(t => !['completed', 'cancelled'].includes(t.status)));
  const done = workflows.filter(t => ['completed', 'cancelled'].includes(t.status));

  return (
    <React.Fragment>
      <div className="quick-add-row" style={{ marginBottom: '16px' }}>
        <input
          type="text" className="quick-add-inp" id="wf-quick-add"
          placeholder="+ New workflow name… (Enter to create)"
          onKeyDown={e => { if (e.key === 'Enter') quickAddWorkflow(e); }}
        />
        <button className="sub-add-btn" style={{ flexShrink: 0 }} onClick={() => quickAddWorkflow()}>Create</button>
      </div>
      {active.length ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {active.map(t => <TaskCard key={t.id} t={t} today={today} clickFn={openTaskPage} />)}
        </div>
      ) : (
        <div className="empty-state" style={{ marginTop: '8px' }}>No active workflows — create one above.</div>
      )}
      {done.length ? (
        <React.Fragment>
          <div className="done-section-hdr" onClick={() => setDoneOpen(o => !o)}>
            <span className={`done-chevron ${doneOpen ? 'open' : ''}`}>▶</span>
            <span>Completed &amp; Cancelled ({done.length})</span>
          </div>
          <div className={`done-list ${doneOpen ? '' : 'collapsed'}`} id="wf-done-list-inner">
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {done.map(t => <TaskCard key={t.id} t={t} today={today} clickFn={openTaskPage} />)}
            </div>
          </div>
        </React.Fragment>
      ) : null}
    </React.Fragment>
  );
}

function PageItem({ b, c, p, activePageId }) {
  const isActive = p.id === activePageId;
  const color = p.color || 'default';
  return (
    <div className={`nb-pg-item ${isActive ? 'active' : ''}`} data-color={color} onClick={() => nbOpenPage(b.id, c.id, p.id)} id={`nbpg-${p.id}`}>
      <div className="nb-pg-dot" style={{ background: NOTE_COLORS[color] || NOTE_COLORS.default }}></div>
      <span className="nb-pg-title" title={p.title || 'Untitled'}>{p.title || 'Untitled'}</span>
      {p.is_locked ? <span className="nb-pg-lock" title="Password protected">🔒</span> : null}
      <div className="nb-pg-acts" onClick={e => e.stopPropagation()}>
        <button className="nb-pg-act-btn" onClick={() => nbDeletePage(b.id, c.id, p.id)} title="Delete page">🗑</button>
      </div>
    </div>
  );
}

function ChapterNode({ b, c, activePageId, nbOpenChapters, nbAddingPage }) {
  const isOpen = nbOpenChapters.has(c.id);
  return (
    <div className="nb-ch" id={`nbch-${c.id}`}>
      <div className="nb-ch-hdr" onClick={() => nbToggleChapter(b.id, c.id)}>
        <span className={`nb-ch-chev ${isOpen ? 'open' : ''}`}>▶</span>
        <span className="nb-ch-icon">📖</span>
        <span className="nb-ch-title" title={c.title}>{c.title}</span>
        <span className="nb-ch-count">{c.pages.length}p</span>
        <div className="nb-ch-acts" onClick={e => e.stopPropagation()}>
          <button className="nb-ch-act-btn" onClick={() => nbStartAddPage(b.id, c.id)} title="Add page">+ Pg</button>
          <button className="nb-ch-act-btn" onClick={() => nbRenameChapter(b.id, c.id)} title="Rename">✏</button>
          <button className="nb-ch-act-btn del" onClick={() => nbDeleteChapter(b.id, c.id)} title="Delete chapter">🗑</button>
        </div>
      </div>
      {isOpen ? (
        <div className="nb-ch-body">
          {c.pages.map(p => <PageItem key={p.id} b={b} c={c} p={p} activePageId={activePageId} />)}
          {nbAddingPage === c.id ? (
            <div className="nb-inline-form" style={{ paddingLeft: '4px' }}>
              <input
                className="nb-inline-inp" id={`nb-pg-inp-${c.id}`} type="text" placeholder="Page title… (Enter)"
                onKeyDown={e => { if (e.key === 'Enter') nbSavePage(b.id, c.id); if (e.key === 'Escape') nbCancelAdd(); }}
              />
              <button className="nb-inline-btn" onClick={() => nbSavePage(b.id, c.id)}>Add</button>
              <button className="nb-inline-cancel" onClick={() => nbCancelAdd()}>✕</button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function BookNode({ b, activePageId, nbOpenBooks, nbOpenChapters, nbAddingChapter, nbAddingPage }) {
  const isOpen = nbOpenBooks.has(b.id);
  const chCnt = b.chapters.length;
  const pgCnt = b.chapters.reduce((s, c) => s + c.pages.length, 0);
  return (
    <div className="nb-book" id={`nbbook-${b.id}`}>
      <div className="nb-book-hdr" onClick={() => nbToggleBook(b.id)}>
        <span className={`nb-book-chev ${isOpen ? 'open' : ''}`}>▶</span>
        <span className="nb-book-icon">📚</span>
        <span className="nb-book-title" title={b.title}>{b.title}</span>
        <span className="nb-book-count">{chCnt}ch · {pgCnt}p</span>
        <div className="nb-book-acts" onClick={e => e.stopPropagation()}>
          <button className="nb-book-act-btn" onClick={() => nbStartAddChapter(b.id)} title="Add chapter">+ Ch</button>
          <button className="nb-book-act-btn" onClick={() => nbRenameBook(b.id)} title="Rename">✏</button>
          <button className="nb-book-act-btn del" onClick={() => nbDeleteBook(b.id)} title="Delete notebook">🗑</button>
        </div>
      </div>
      {isOpen ? (
        <div className="nb-book-body">
          {b.chapters.map(c => <ChapterNode key={c.id} b={b} c={c} activePageId={activePageId} nbOpenChapters={nbOpenChapters} nbAddingPage={nbAddingPage} />)}
          {nbAddingChapter === b.id ? (
            <div className="nb-inline-form">
              <input
                className="nb-inline-inp" id={`nb-ch-inp-${b.id}`} type="text" placeholder="Chapter name… (Enter)"
                onKeyDown={e => { if (e.key === 'Enter') nbSaveChapter(b.id); if (e.key === 'Escape') nbCancelAdd(); }}
              />
              <button className="nb-inline-btn" onClick={() => nbSaveChapter(b.id)}>Add</button>
              <button className="nb-inline-cancel" onClick={() => nbCancelAdd()}>✕</button>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function NoteSearchResults({ activePageId, noteSearchQ }) {
  const q = noteSearchQ.toLowerCase();
  const hits = allPagesFlat().filter(({ page }) => (page.title || '').toLowerCase().includes(q) || noteBodyText(page.body || '').toLowerCase().includes(q));
  if (!hits.length) {
    return <div className="nb-empty"><span className="nb-empty-icon">🔍</span>No pages match "{noteSearchQ}"</div>;
  }
  return (
    <div>
      {hits.map(({ book: b, chapter: c, page: p }) => (
        <div key={p.id} className={`nb-sr-item ${p.id === activePageId ? 'active' : ''}`} onClick={() => nbOpenPage(b.id, c.id, p.id)}>
          <div className="nb-sr-title">{p.title || 'Untitled'}{p.is_locked ? ' 🔒' : ''}</div>
          <div className="nb-sr-path">📚 {b.title} › 📖 {c.title}</div>
          <div className="nb-sr-preview">{p.is_locked ? 'Password protected' : noteBodyText(p.body || '').slice(0, 100).trim()}</div>
        </div>
      ))}
    </div>
  );
}

function NoteTree({ allBooks, activePageId, noteSearchQ, nbOpenBooks, nbOpenChapters, nbAddingChapter, nbAddingPage }) {
  if (noteSearchQ) return <NoteSearchResults activePageId={activePageId} noteSearchQ={noteSearchQ} />;
  if (!allBooks.length) {
    return <div className="nb-empty"><span className="nb-empty-icon">📚</span>No notebooks yet<br />Click <b>+</b> to create your first notebook</div>;
  }
  return (
    <React.Fragment>
      {allBooks.map(b => (
        <BookNode key={b.id} b={b} activePageId={activePageId} nbOpenBooks={nbOpenBooks} nbOpenChapters={nbOpenChapters} nbAddingChapter={nbAddingChapter} nbAddingPage={nbAddingPage} />
      ))}
    </React.Fragment>
  );
}

function DashMiniList({ tasks, today }) {
  if (!tasks.length) return <div className="dash-empty">No tasks</div>;
  const shown = tasks.slice(0, 5);
  return (
    <React.Fragment>
      {shown.map(t => {
        const isDoneLike = ['completed', 'cancelled'].includes(t.status);
        const dc = !t.due_date || isDoneLike ? '' : t.due_date < today ? 'due-o' : t.due_date === today ? 'due-t' : 'due-n';
        const dl = !t.due_date || isDoneLike ? '' : t.due_date < today ? '⚠ Overdue' : t.due_date === today ? 'Today' : fmtDue(t.due_date);
        return (
          <div className="dash-task" key={t.id} onClick={() => openPanel(t.id)}>
            <span className={`pdot p-${t.priority}`} style={{ width: 6, height: 6, marginTop: 0, flexShrink: 0 }}></span>
            <span className="dt-title">{t.title}</span>
            {dl ? <span className={`due-chip ${dc}`} style={{ fontSize: '.6rem' }}>{dl}</span> : null}
            <span className={`sb sb-${t.status}`} style={{ fontSize: '.6rem', padding: '2px 5px' }} onClick={e => { e.stopPropagation(); showStatusMenu(e, t.id); }}>
              <span className="sdot"></span>{SL[t.status]}
            </span>
          </div>
        );
      })}
      {tasks.length > 5 ? <div className="dash-empty">+{tasks.length - 5} more</div> : null}
    </React.Fragment>
  );
}

function Dashboard({ allTasks, currentFilter, today }) {
  const standalone = allTasks.filter(t => t.task_type !== 'workflow' && !t.step_id);
  const counts = Object.fromEntries(Object.keys(SL).map(s => [s, 0]));
  standalone.forEach(t => { if (counts[t.status] !== undefined) counts[t.status]++; });
  const total = standalone.length, done = counts.completed, pct = total ? Math.round(done / total * 100) : 0;
  const overdue = standalone.filter(t => t.due_date && t.due_date < today && !['completed', 'cancelled'].includes(t.status)).length;
  const hi = standalone.filter(t => t.priority === 'high' && !['completed', 'cancelled'].includes(t.status));
  const byP = arr => [...arr].sort((a, b) => PO[b.priority] - PO[a.priority]);
  const todoT = byP(standalone.filter(t => t.status === 'todo'));
  const inPT = byP(standalone.filter(t => t.status === 'in_process'));

  return (
    <React.Fragment>
      <div className="stat-grid">
        {Object.entries(SL).map(([s, l]) => (
          <div key={s} className={`stat-card sc-${s} ${currentFilter === s ? 'af' : ''}`} onClick={() => setFilterCard(s)}>
            <div className="stat-count">{counts[s]}</div><div className="stat-label">{l}</div>
          </div>
        ))}
      </div>
      <div className="progress-row">
        <div className="progress-track"><div className="progress-fill" style={{ width: `${pct}%` }}></div></div>
        <span className="progress-label">{done}/{total} complete · {pct}%</span>
        {overdue ? <span className="overdue-pill">⚠ {overdue} overdue</span> : null}
      </div>
      {hi.length ? (
        <div className="hprio-section">
          <div className="hprio-hdr">🔴 High Priority ({hi.length})</div>
          <div className="hprio-list">
            {hi.map(t => <div className="hprio-chip" key={t.id} onClick={() => openPanel(t.id)}><span>{t.title}</span></div>)}
          </div>
        </div>
      ) : null}
      <div className="dash-panels">
        <div className="dash-panel">
          <div className="panel-hdr"><span style={{ color: '#3b82f6', fontSize: '.65rem' }}>●</span><span className="panel-ttl">To Do</span><span className="panel-cnt">{todoT.length}</span></div>
          <DashMiniList tasks={todoT} today={today} />
        </div>
        <div className="dash-panel">
          <div className="panel-hdr"><span style={{ color: '#22c55e', fontSize: '.65rem' }}>●</span><span className="panel-ttl">In Process</span><span className="panel-cnt">{inPT.length}</span></div>
          <DashMiniList tasks={inPT} today={today} />
        </div>
      </div>
    </React.Fragment>
  );
}

let __dashboardRoot = null;
let __listRoot = null;
let __todayRoot = null;
let __next7Root = null;
let __kanbanRoot = null;
let __calendarRoot = null;
let __remindersRoot = null;
let __workflowsRoot = null;

window.TFReact = {
  renderDashboard() {
    const el = document.getElementById('dashboard');
    if (!el) return;
    if (!__dashboardRoot) __dashboardRoot = ReactDOM.createRoot(el);
    __dashboardRoot.render(<Dashboard allTasks={allTasks} currentFilter={currentFilter} today={todayStr()} />);
  },
  renderList() {
    const el = document.getElementById('view-list');
    if (!el) return;
    const tasks = getVisible(), today = todayStr();
    if (!__listRoot) __listRoot = ReactDOM.createRoot(el);
    __listRoot.render(
      <ListView tasks={tasks} today={today} groupByProject={groupByProject} selectMode={selectMode} selectedIds={selectedIds} panelTaskId={panelTaskId} />
    );
  },
  renderToday() {
    const el = document.getElementById('view-today');
    if (!el) return;
    if (!__todayRoot) __todayRoot = ReactDOM.createRoot(el);
    __todayRoot.render(<TodayView allTasks={allTasks} allMeetings={allMeetings} today={todayStr()} />);
  },
  renderNext7() {
    const el = document.getElementById('view-next7');
    if (!el) return;
    if (!__next7Root) __next7Root = ReactDOM.createRoot(el);
    __next7Root.render(<Next7View allTasks={allTasks} today={todayStr()} />);
  },
  renderKanban() {
    const el = document.getElementById('view-kanban');
    if (!el) return;
    if (!__kanbanRoot) __kanbanRoot = ReactDOM.createRoot(el);
    __kanbanRoot.render(<KanbanBoard allTasks={allTasks} today={todayStr()} />);
  },
  renderCalendar() {
    const el = document.getElementById('view-calendar');
    if (!el) return;
    if (!__calendarRoot) __calendarRoot = ReactDOM.createRoot(el);
    __calendarRoot.render(<CalendarView allTasks={allTasks} allMeetings={allMeetings} calYear={calYear} calMonth={calMonth} today={todayStr()} />);
  },
  renderReminders() {
    const el = document.getElementById('view-reminders');
    if (!el) return;
    if (!__remindersRoot) __remindersRoot = ReactDOM.createRoot(el);
    __remindersRoot.render(<RemindersView allTasks={allTasks} allStandaloneReminders={allStandaloneReminders} today={todayStr()} />);
  },
  renderWorkflows() {
    const el = document.getElementById('view-workflows');
    if (!el) return;
    if (!__workflowsRoot) __workflowsRoot = ReactDOM.createRoot(el);
    __workflowsRoot.render(<WorkflowsView allTasks={allTasks} today={todayStr()} />);
  },
  renderBookTree() {
    // #nb-tree is recreated by renderNotes()'s innerHTML rebuild every time the Notes
    // view is (re-)entered, so — unlike the other views — we can't cache a root across
    // calls here; a stale root would point at a detached node. Fresh root each call.
    const el = document.getElementById('nb-tree');
    if (!el) return;
    ReactDOM.createRoot(el).render(
      <NoteTree
        allBooks={allBooks} activePageId={activePageId} noteSearchQ={noteSearchQ}
        nbOpenBooks={nbOpenBooks} nbOpenChapters={nbOpenChapters}
        nbAddingChapter={nbAddingChapter} nbAddingPage={nbAddingPage}
      />
    );
  },
};

if (window.__resolveTFReactReady) window.__resolveTFReactReady();
