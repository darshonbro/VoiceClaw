document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const tabButtons = document.querySelectorAll('.tab-btn');
  const docPanes = document.querySelectorAll('.doc-pane');
  const tocList = document.getElementById('tocList');
  const searchInput = document.getElementById('policySearch');
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');
  
  const dataModal = document.getElementById('dataModal');
  const btnOpenDataModal = document.getElementById('btnOpenDataModal');
  const btnCloseDataModal = document.getElementById('btnCloseDataModal');
  const btnCancelModal = document.getElementById('btnCancelModal');
  const footerNavLinks = document.querySelectorAll('.footer-nav');

  // Active Tab state
  let currentActiveTab = 'privacy';

  // Function to show toast
  function showToast(message) {
    if (!toast) return;
    toastMsg.textContent = message;
    toast.classList.add('show');
    setTimeout(() => {
      toast.classList.remove('show');
    }, 2800);
  }

  // Populate Table of Contents for the active pane
  function updateTOC(paneId) {
    if (!tocList) return;
    tocList.innerHTML = '';
    const activePane = document.getElementById(`pane-${paneId}`);
    if (!activePane) return;

    const cards = activePane.querySelectorAll('.policy-card');
    cards.forEach((card, index) => {
      const heading = card.querySelector('h2');
      const cardId = card.id;
      if (heading && cardId) {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.href = `#${cardId}`;
        a.className = 'toc-link' + (index === 0 ? ' active' : '');
        a.textContent = heading.textContent;
        
        a.addEventListener('click', (e) => {
          e.preventDefault();
          document.querySelectorAll('.toc-link').forEach(l => l.classList.remove('active'));
          a.classList.add('active');
          const targetEl = document.getElementById(cardId);
          if (targetEl) {
            targetEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        });

        li.appendChild(a);
        tocList.appendChild(li);
      }
    });
  }

  // Tab switching logic
  function switchTab(targetTab) {
    currentActiveTab = targetTab;
    
    // Update button states
    tabButtons.forEach(btn => {
      if (btn.dataset.tab === targetTab) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    // Update Panes
    docPanes.forEach(pane => {
      if (pane.id === `pane-${targetTab}`) {
        pane.classList.add('active');
      } else {
        pane.classList.remove('active');
      }
    });

    // Clear search and reset cards visibility
    if (searchInput) {
      searchInput.value = '';
      resetCardFilter();
    }

    // Refresh TOC
    updateTOC(targetTab);

    // Scroll to top of layout smoothly
    const layout = document.querySelector('.content-layout');
    if (layout) {
      layout.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  // Tab Button click event listeners
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });

  // Footer nav links
  footerNavLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const target = link.dataset.tab;
      if (target) switchTab(target);
    });
  });

  // Copy anchor link
  document.addEventListener('click', (e) => {
    const copyBtn = e.target.closest('.copy-anchor');
    if (copyBtn) {
      const anchorId = copyBtn.dataset.anchor;
      const fullUrl = `${window.location.origin}${window.location.pathname}#${anchorId}`;
      navigator.clipboard.writeText(fullUrl).then(() => {
        showToast('Direct clause link copied to clipboard!');
      }).catch(() => {
        showToast('Copied section identifier: #' + anchorId);
      });
    }
  });

  // Live Clause Search / Filter
  function resetCardFilter() {
    const activePane = document.getElementById(`pane-${currentActiveTab}`);
    if (!activePane) return;
    const cards = activePane.querySelectorAll('.policy-card');
    cards.forEach(card => card.style.display = 'block');
  }

  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase().trim();
      const activePane = document.getElementById(`pane-${currentActiveTab}`);
      if (!activePane) return;
      
      const cards = activePane.querySelectorAll('.policy-card');
      cards.forEach(card => {
        const text = card.textContent.toLowerCase();
        if (text.includes(query)) {
          card.style.display = 'block';
        } else {
          card.style.display = 'none';
        }
      });
    });
  }

  // Data Modal Handlers
  function openModal() {
    if (dataModal) dataModal.classList.add('open');
  }
  function closeModal() {
    if (dataModal) dataModal.classList.remove('open');
  }

  if (btnOpenDataModal) btnOpenDataModal.addEventListener('click', openModal);
  if (btnCloseDataModal) btnCloseDataModal.addEventListener('click', closeModal);
  if (btnCancelModal) btnCancelModal.addEventListener('click', closeModal);

  if (dataModal) {
    dataModal.addEventListener('click', (e) => {
      if (e.target === dataModal) closeModal();
    });
  }

  // Handle URL path or hash on load
  const pathname = window.location.pathname.toLowerCase();
  const hash = window.location.hash;

  if (pathname.includes('/terms') || (hash && hash.includes('terms-'))) {
    switchTab('terms');
  } else if (pathname.includes('/data') || (hash && hash.includes('sec-'))) {
    switchTab('data-practices');
  } else {
    switchTab('privacy');
  }

  if (hash) {
    const cleanHash = hash.replace('#', '');
    setTimeout(() => {
      const targetElem = document.getElementById(cleanHash);
      if (targetElem) {
        targetElem.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 250);
  }
});
