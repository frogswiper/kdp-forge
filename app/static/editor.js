// kdp-forge editor — Quill 2.x + debounced autosave + snapshots.
(function () {
  const article = document.querySelector('article[data-chapter-id]');
  const slug = document.body.dataset.slug;
  if (!article) return setupSnapshots(slug);

  const chapterId = Number(article.dataset.chapterId);
  const editorEl = document.getElementById('editor');
  const titleEl = document.getElementById('chapter-title');
  const kindEl = document.getElementById('chapter-kind');
  const statusEl = document.getElementById('save-status');
  const wordEl = document.getElementById('current-word-count');
  const bookWordEl = document.getElementById('book-word-count');
  const tpl = document.getElementById('initial-html');
  const initialHTML = tpl ? tpl.innerHTML.trim() : '';

  kindEl.value = kindEl.dataset.current;

  const quill = new Quill(editorEl, {
    theme: 'snow',
    placeholder: 'Begin writing…',
    modules: {
      toolbar: [
        [{ header: [false, 2, 3] }],
        ['bold', 'italic', 'underline'],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['blockquote'],
        ['link'],
        ['clean'],
      ],
    },
  });
  if (initialHTML) {
    // setContents preserves formatting better than dangerouslyPasteHTML for round-tripping
    const delta = quill.clipboard.convert({ html: initialHTML });
    quill.setContents(delta, 'silent');
  }

  let timer = null;
  let dirty = false;
  let inflight = false;
  let pendingPayload = null;

  function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = 'save-status ' + (cls || '');
  }

  function collectPayload() {
    return {
      html: quill.root.innerHTML,
      title: titleEl.textContent.trim(),
      kind: kindEl.value,
    };
  }

  async function save() {
    if (inflight) {
      pendingPayload = collectPayload();
      return;
    }
    const payload = collectPayload();
    inflight = true;
    setStatus('saving…', 'saving');
    try {
      const r = await fetch(`/api/chapters/${chapterId}`, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      updateWordCounts(data.word_count);
      updateSidebarChapter(data);
      dirty = false;
      setStatus('saved', 'ok');
    } catch (err) {
      console.error('save failed', err);
      setStatus('error — retry in 5s', 'error');
      setTimeout(() => { dirty = true; scheduleSave(0); }, 5000);
    } finally {
      inflight = false;
      if (pendingPayload) {
        pendingPayload = null;
        scheduleSave(50);
      }
    }
  }

  function scheduleSave(delay = 1500) {
    dirty = true;
    setStatus('editing…', 'dirty');
    clearTimeout(timer);
    timer = setTimeout(save, delay);
  }

  function updateWordCounts(currentWords) {
    const sidebarLi = document.querySelector(`.chapter-item[data-chapter-id="${chapterId}"]`);
    let oldCount = 0;
    if (sidebarLi) {
      const w = sidebarLi.querySelector('.ch-words');
      oldCount = parseInt((w.textContent || '0').replace(/,/g, ''), 10) || 0;
      w.textContent = currentWords.toLocaleString();
    }
    wordEl.textContent = currentWords.toLocaleString();
    const bookOld = parseInt((bookWordEl.textContent || '0').replace(/,/g, ''), 10) || 0;
    bookWordEl.textContent = (bookOld - oldCount + currentWords).toLocaleString();
  }

  function updateSidebarChapter(data) {
    const sidebarLi = document.querySelector(`.chapter-item[data-chapter-id="${chapterId}"]`);
    if (!sidebarLi) return;
    sidebarLi.className = sidebarLi.className
      .replace(/\bkind-\S+/g, '')
      .replace(/\s+/g, ' ').trim();
    sidebarLi.classList.add(`kind-${data.kind}`);
    const titleSpan = sidebarLi.querySelector('.ch-title');
    if (titleSpan) titleSpan.textContent = data.title;
    const meta = sidebarLi.querySelector('.ch-meta');
    if (meta) {
      meta.innerHTML = `<span class="ch-words">${data.word_count.toLocaleString()}</span>w &middot; ${data.kind.replace(/_/g, ' ')}`;
    }
  }

  quill.on('text-change', (_, __, source) => {
    if (source === 'user') scheduleSave();
  });
  titleEl.addEventListener('input', () => scheduleSave(800));
  kindEl.addEventListener('change', () => scheduleSave(0));

  // Prevent accidental nav loss.
  window.addEventListener('beforeunload', (e) => {
    if (dirty || inflight) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  setupSnapshots(slug);
  setupPdfTrigger(slug);
  setupChapterAI(chapterId);

  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function setupChapterAI(chapterId) {
    const modal = document.getElementById('ai-modal');
    const modalTitle = document.getElementById('ai-modal-title');
    const modalBody = document.getElementById('ai-modal-body');
    if (!modal) return;
    document.getElementById('ai-modal-close').addEventListener('click', () => modal.close());

    const titles = { copyedit: 'Copyedit suggestions', critique: 'Chapter critique', hook: 'Hook check' };

    async function run(tool) {
      modalTitle.textContent = titles[tool] || 'AI';
      modalBody.innerHTML = '<p class="muted">Asking the model… (10–60 sec)</p>';
      modal.showModal();
      // Save any pending edits before asking the model — so it sees the current text.
      if (dirty || inflight) {
        await save();
      }
      try {
        const r = await fetch(`/api/chapters/${chapterId}/ai/${tool}`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: '{}',
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
        const data = await r.json();
        if (tool === 'copyedit') renderCopyedit(data);
        else if (tool === 'critique') renderCritique(data);
        else if (tool === 'hook') renderHook(data);
      } catch (e) {
        modalBody.innerHTML = `<p class="error">Error: ${escapeHtml(String(e.message || e))}</p>`;
      }
    }

    function renderCopyedit(data) {
      const edits = data.edits || [];
      if (!edits.length) {
        modalBody.innerHTML = '<p class="muted">No suggested edits — the chapter looks clean.</p>';
        return;
      }
      modalBody.innerHTML = edits.map((e, i) => `
        <article class="ai-card">
          <header><strong>#${i+1}</strong> <span class="muted">${escapeHtml(e.kind || 'edit')}</span></header>
          <p><span class="diff-del">${escapeHtml(e.original || '')}</span> → <span class="diff-ins">${escapeHtml(e.suggestion || '')}</span></p>
          <p class="muted small">${escapeHtml(e.reason || '')}</p>
          <button type="button" class="ai-pick" data-orig="${escapeHtml(e.original || '')}" data-sug="${escapeHtml(e.suggestion || '')}">Apply</button>
        </article>
      `).join('');
      modalBody.querySelectorAll('.ai-pick').forEach(btn => btn.addEventListener('click', () => {
        const orig = btn.dataset.orig;
        const sug = btn.dataset.sug;
        const root = quill.root;
        const original = root.innerHTML;
        const replaced = original.replace(orig, sug);
        if (replaced === original) {
          btn.textContent = 'not found';
          btn.disabled = true;
          return;
        }
        const delta = quill.clipboard.convert({ html: replaced });
        quill.setContents(delta, 'user');
        btn.textContent = 'applied';
        btn.disabled = true;
        scheduleSave(200);
      }));
    }

    function renderCritique(data) {
      const sect = (key, label) => {
        const s = data[key] || {};
        const obs = (s.observations || []).map(o => `<li>${escapeHtml(o)}</li>`).join('');
        return `
          <article class="ai-card">
            <header><strong>${label}</strong></header>
            <p><em>${escapeHtml(s.verdict || '')}</em></p>
            ${obs ? `<ul class="ai-list">${obs}</ul>` : ''}
            ${s.suggestion ? `<p class="muted small">Suggestion: ${escapeHtml(s.suggestion)}</p>` : ''}
          </article>
        `;
      };
      modalBody.innerHTML = `
        <p class="ai-score">Overall: <strong>${escapeHtml(String(data.overall_score ?? '?'))}/10</strong></p>
        <p>${escapeHtml(data.overall_summary || '')}</p>
        ${sect('hook', 'Hook')}
        ${sect('pacing', 'Pacing')}
        ${sect('dialogue', 'Dialogue')}
        ${sect('ending', 'Ending')}
      `;
    }

    function renderHook(data) {
      const lines = (data.alternative_first_lines || []).map(l => `<li>${escapeHtml(l)}</li>`).join('');
      const working = (data.working || []).map(o => `<li>${escapeHtml(o)}</li>`).join('');
      const sharper = (data.sharper || []).map(o => `<li>${escapeHtml(o)}</li>`).join('');
      modalBody.innerHTML = `
        <p class="ai-score">Hook score: <strong>${escapeHtml(String(data.score ?? '?'))}/10</strong></p>
        <article class="ai-card">
          <header><strong>What's working</strong></header>
          ${working ? `<ul class="ai-list">${working}</ul>` : '<p class="muted">—</p>'}
        </article>
        <article class="ai-card">
          <header><strong>Could be sharper</strong></header>
          ${sharper ? `<ul class="ai-list">${sharper}</ul>` : '<p class="muted">—</p>'}
        </article>
        <article class="ai-card">
          <header><strong>Alternative first lines</strong></header>
          ${lines ? `<ol class="ai-list">${lines}</ol>` : '<p class="muted">—</p>'}
        </article>
      `;
    }

    document.querySelectorAll('.ai-btn').forEach(b => b.addEventListener('click', () => run(b.dataset.aiTool)));
  }

  function setupPdfTrigger(slug) {
    const btn = document.getElementById('pdf-trigger');
    const trim = document.getElementById('pdf-trim');
    const pages = document.getElementById('pdf-pages');
    if (!btn || !trim || !pages) return;
    btn.addEventListener('click', () => {
      const url = `/api/books/${slug}/export.pdf?trim=${encodeURIComponent(trim.value)}&pages=${encodeURIComponent(pages.value)}`;
      window.location.href = url;
    });
  }

  function setupSnapshots(slug) {
    const createBtn = document.getElementById('snap-create');
    const list = document.getElementById('snap-list');
    if (createBtn) {
      createBtn.addEventListener('click', async () => {
        const label = prompt('Snapshot label (optional):', '');
        if (label === null) return;
        const r = await fetch(`/api/books/${slug}/snapshots`, {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ label }),
        });
        if (r.ok) location.reload();
        else alert('Snapshot failed: ' + await r.text());
      });
    }
    if (list) {
      list.addEventListener('click', async (e) => {
        const restoreBtn = e.target.closest('.snap-restore');
        const deleteBtn = e.target.closest('.snap-delete');
        const li = e.target.closest('li[data-snap-id]');
        if (!li) return;
        const id = li.dataset.snapId;
        if (restoreBtn) {
          if (!confirm('Restore this snapshot? Current chapters will be saved as an auto-snapshot first.')) return;
          const r = await fetch(`/api/books/${slug}/snapshots/${id}/restore`, { method: 'POST' });
          if (r.ok) location.reload();
          else alert('Restore failed: ' + await r.text());
        } else if (deleteBtn) {
          if (!confirm('Delete this snapshot?')) return;
          const r = await fetch(`/api/books/${slug}/snapshots/${id}/delete`, { method: 'POST' });
          if (r.ok) li.remove();
        }
      });
    }
  }
})();
