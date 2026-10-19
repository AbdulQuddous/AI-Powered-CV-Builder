/* M8's template supplies the design; draft content stays in this browser.
   These presentation helpers follow M8 context_builder, without changing CV JSON. */
(function (global) {
  'use strict';
  const text = value => ['string', 'number'].includes(typeof value) ? String(value).trim() : '';
  const first = (item, ...keys) => keys.map(key => text(item?.[key])).find(Boolean) || '';
  const strings = value => Array.isArray(value)
    ? value.map(item => item && typeof item === 'object'
      ? first(item, 'name', 'title', 'text', 'value') : text(item)).filter(Boolean) : [];
  const join = (...values) => values.filter(Boolean).join(' | ');
  const dates = item => {
    const start = first(item, 'start_date');
    const end = item.is_current ? 'Present' : first(item, 'end_date');
    return start && end ? `${start} - ${end}` : start || end;
  };

  function entry(section, item) {
    if (typeof item === 'string') return {title: item.trim(), subtitle: '', description: '', bullets: []};
    if (!item || typeof item !== 'object' || Array.isArray(item)) return null;
    const row = {title: '', subtitle: '', description: '', bullets: []};
    switch (section) {
      case 'experience':
        row.title = first(item, 'job_title', 'role', 'position', 'title');
        row.subtitle = join(first(item, 'company', 'organization'), first(item, 'location'), dates(item));
        row.description = first(item, 'description');
        row.bullets = strings(item.highlights?.length ? item.highlights : item.responsibilities);
        break;
      case 'education':
        row.title = first(item, 'degree');
        row.subtitle = join(first(item, 'institution'), first(item, 'field_of_study'), dates(item));
        if (first(item, 'grade')) row.description = `Grade: ${first(item, 'grade')}`;
        break;
      case 'projects': {
        row.title = first(item, 'name', 'title');
        row.description = first(item, 'description');
        const technologies = strings(typeof item.technologies === 'string'
          ? item.technologies.split(',') : item.technologies);
        if (technologies.length) row.subtitle = `Technologies: ${technologies.join(', ')}`;
        row.bullets = strings(item.highlights);
        if (first(item, 'url')) row.bullets.push(first(item, 'url'));
        break;
      }
      case 'certifications':
        row.title = first(item, 'name', 'title', 'certification');
        row.subtitle = join(first(item, 'issuer', 'organization'), first(item, 'date', 'issue_date'));
        if (first(item, 'url')) row.bullets.push(first(item, 'url'));
        break;
      case 'achievements':
        row.title = first(item, 'title', 'name');
        row.description = first(item, 'description', 'details');
        break;
      case 'languages':
        row.title = first(item, 'name', 'language');
        row.subtitle = first(item, 'proficiency', 'level');
        break;
    }
    return row;
  }

  function context(cv) {
    const sections = [
      ['experience', 'Professional Experience'], ['projects', 'Projects'],
      ['education', 'Education'], ['certifications', 'Certifications'],
      ['achievements', 'Achievements'], ['languages', 'Languages']
    ].map(([key, label]) => ({key, label, items: (Array.isArray(cv[key]) ? cv[key] : [])
      .map(item => entry(key, item))
      .filter(row => row && (row.title || row.subtitle || row.description || row.bullets.length))
    })).filter(section => section.items.length);
    return {
      name: text(cv.personal?.full_name) || 'Curriculum Vitae',
      targetRole: text(cv.meta?.target_role),
      contact: ['email', 'phone', 'location', 'linkedin', 'github', 'portfolio']
        .map(key => text(cv.personal?.[key])).filter(Boolean),
      summary: text(cv.summary), skills: strings(cv.skills), sections
    };
  }

  function render(document, cv) {
    const main = document.querySelector('.document');
    if (!main) throw new Error('The selected template cannot display a live preview.');
    const data = context(cv);
    const fragment = document.createDocumentFragment();
    function add(parent, tag, className, content) {
      const node = document.createElement(tag);
      node.className = className;
      if (content !== undefined) node.textContent = content;
      parent.appendChild(node);
      return node;
    }
    const header = add(fragment, 'header', 'header');
    header.id = 'm7-preview-personal';
    add(header, 'h1', 'name', data.name);
    if (data.targetRole) add(header, 'div', 'target-role', data.targetRole);
    if (data.contact.length) add(header, 'div', 'contact', data.contact.join(' | '));
    const design = document.body?.dataset || {};
    const sideKeys = (design.sideKeys || '').split(',').filter(Boolean);
    const order = (design.sectionOrder || '').split(',').filter(Boolean);
    let mainColumn = fragment, sideColumn = null;
    if (order.length) {
      const layout = add(fragment, 'div', 'layout');
      mainColumn = add(layout, 'div', 'main-column');
      if (sideKeys.length) sideColumn = add(layout, 'aside', 'side-column');
    }
    const nodes = {};
    function section(key, label) {
      const node = document.createElement('section');
      node.className = 'section';
      if (node.dataset) node.dataset.section = key;
      nodes[key] = node;
      if (!order.length) fragment.appendChild(node);
      node.id = `m7-preview-${key}`;
      add(node, 'h2', 'section-title', label);
      return node;
    }
    if (data.summary) add(section('summary', 'Professional Summary'), 'p', 'summary', data.summary);
    if (data.skills.length) {
      const skills = add(section('skills', 'Skills'), 'p', 'skills');
      if (order.length) data.skills.forEach(skill => add(skills, 'span', 'skill', skill));
      else skills.textContent = data.skills.join(', ');
    }
    for (const group of data.sections) {
      const node = section(group.key, group.label);
      for (const row of group.items) {
        const block = add(node, 'div', 'entry');
        if (row.title) add(block, 'div', 'entry-title', row.title);
        if (row.subtitle) add(block, 'div', 'entry-subtitle', row.subtitle);
        if (row.description) add(block, 'p', 'entry-description', row.description);
        if (row.bullets.length) {
          const list = add(block, 'ul', '');
          row.bullets.forEach(bullet => add(list, 'li', '', bullet));
        }
      }
    }
    for (const key of order) {
      if (nodes[key]) (sideKeys.includes(key) && sideColumn ? sideColumn : mainColumn).appendChild(nodes[key]);
    }
    main.replaceChildren(fragment);
    document.title = `${data.name} - CV`;
  }

  function create({frame, viewport, stage, panel, toolbar, request, getCV, onReady, onError, initialZoom = 'fit'}) {
    let disposed = false;
    let ready = false;
    let zoom = initialZoom;
    let scale = 1;
    let pendingSection = null;
    const pageWidth = 210 * 96 / 25.4;
    const pageHeight = 297 * 96 / 25.4;
    function fit() {
      if (disposed || !ready) return;
      const document = frame.contentDocument;
      if (!document) return;
      // Reset height so removing content can shrink a previously long CV.
      frame.style.height = `${pageHeight}px`;
      const height = Math.max(pageHeight, document.documentElement.scrollHeight, document.body.scrollHeight);
      scale = zoom === 'fit' ? Math.min(1, viewport.clientWidth / pageWidth) : zoom;
      frame.style.height = `${height}px`;
      frame.style.transform = `scale(${scale})`;
      stage.style.height = `${height * scale}px`;
      stage.style.width = `${pageWidth * scale}px`;
    }
    function revealSection() {
      if (disposed || !ready || !pendingSection) return;
      const target = frame.contentDocument.getElementById(`m7-preview-${pendingSection}`);
      // Empty sections stay absent until the user adds content.
      if (!target) return;
      pendingSection = null;
      const heading = target.querySelector('.section-title, .name') || target;
      const scroller = panel && panel.scrollHeight > panel.clientHeight + 1 ? panel : viewport;
      const bounds = scroller.getBoundingClientRect();
      const top = bounds.top + (scroller === panel ? toolbar?.offsetHeight || 0 : 0) + 12;
      const bottom = bounds.bottom - 12;
      const frameBounds = frame.getBoundingClientRect();
      const headingBounds = heading.getBoundingClientRect();
      const headingTop = frameBounds.top + headingBounds.top * scale;
      const headingBottom = frameBounds.top + headingBounds.bottom * scale;
      if (headingTop >= top && headingBottom <= bottom) return;
      const reducedMotion = global.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      scroller.scrollTo({
        top: Math.max(0, scroller.scrollTop + headingTop - top),
        behavior: reducedMotion ? 'instant' : 'smooth'
      });
    }
    function update() {
      if (disposed || !ready) return;
      try {
        render(frame.contentDocument, getCV());
        fit();
        revealSection();
      } catch (error) { onError(error); }
    }
    function loaded() {
      if (disposed || !frame.contentDocument?.querySelector('.document')) return;
      const doc = frame.contentDocument;
      if (doc.head && !doc.getElementById('m7-embed-style')) {
        const style = doc.createElement('style'); style.id = 'm7-embed-style';
        style.textContent = 'html{overflow:hidden;background:white!important}body{padding:0!important;background:white!important}.document{margin:0!important;box-shadow:none!important}';
        doc.head.appendChild(style);
      }
      ready = true;
      update();
      onReady();
    }
    frame.addEventListener('load', loaded);
    const observer = global.ResizeObserver ? new global.ResizeObserver(fit) : null;
    observer?.observe(viewport);
    if (!observer) global.addEventListener?.('resize', fit);
    return {
      async load() {
        try {
          const response = await request();
          const markup = await response.text();
          if (disposed) return;
          // Retain M8's selected theme and CSS; remove only the viewer's outer gutter.
          const parsed = new global.DOMParser().parseFromString(markup, 'text/html');
          if (!parsed.querySelector('.document')) throw new Error('CV preview returned an invalid template.');
          const style = parsed.createElement('style');
          style.textContent = 'body { margin: 0; padding: 0; background: white; } .document { box-shadow: none; }';
          parsed.head.appendChild(style);
          frame.srcdoc = '<!doctype html>\n' + parsed.documentElement.outerHTML;
        } catch (error) { if (!disposed) onError(error); }
      },
      update,
      scrollToSection(section) {
        if (!['personal', 'summary', 'skills', 'experience', 'projects', 'education',
          'certifications', 'achievements', 'languages'].includes(section)) return;
        pendingSection = section;
        revealSection();
      },
      setZoom(value) {
        if (!['fit', 1, 1.25].includes(value)) return;
        zoom = value;
        fit();
      },
      destroy() {
        disposed = true;
        observer?.disconnect();
        if (!observer) global.removeEventListener?.('resize', fit);
        frame.removeEventListener('load', loaded);
        frame.removeAttribute('srcdoc');
      }
    };
  }
  global.M7LivePreview = {context, render, create};
  if (typeof module !== 'undefined' && module.exports) module.exports = global.M7LivePreview;
})(typeof window !== 'undefined' ? window : globalThis);
