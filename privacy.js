/**
 * VoiceClaw - Terms of Service & Privacy Policy Engine
 * Features:
 * - Dynamic Tab Switching (Privacy, Terms, Data Practices)
 * - Auto-Generating Sticky Table of Contents (TOC) with ScrollSpy
 * - Real-Time Search Filter with Highlight
 * - One-Click Section Anchor Copy + Toast Notification
 * - GDPR / CCPA Data Deletion Modal Manager
 */

document.addEventListener("DOMContentLoaded", () => {
  // Elements
  const tabButtons = document.querySelectorAll(".tab-btn");
  const docPanes = document.querySelectorAll(".doc-pane");
  const tocList = document.getElementById("tocList");
  const tocTitle = document.getElementById("tocTitle");
  const searchInput = document.getElementById("policySearch");
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toastMsg");

  // Data Modal Elements
  const btnOpenDataModal = document.getElementById("btnOpenDataModal");
  const btnCloseDataModal = document.getElementById("btnCloseDataModal");
  const btnCancelModal = document.getElementById("btnCancelModal");
  const dataModal = document.getElementById("dataModal");

  let currentActiveTab = "privacy";

  // --- 1. Tab Switching Engine ---
  function switchTab(targetTab) {
    if (!targetTab) return;
    currentActiveTab = targetTab;

    // Update Tab Buttons
    tabButtons.forEach(btn => {
      if (btn.dataset.tab === targetTab) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    // Update Document Panes
    docPanes.forEach(pane => {
      if (pane.id === `pane-${targetTab}`) {
        pane.classList.add("active");
      } else {
        pane.classList.remove("active");
      }
    });

    // Update URL Hash without jump
    history.replaceState(null, null, `#${targetTab}`);

    // Rebuild TOC for this tab
    buildTOC(targetTab);

    // Reset search
    if (searchInput) {
      searchInput.value = "";
      filterSections("");
    }
  }

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      switchTab(btn.dataset.tab);
    });
  });

  // Footer Links with data-tab
  document.querySelectorAll(".footer-nav").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(link.dataset.tab);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  // Check URL Hash on load
  const initialHash = window.location.hash.replace("#", "").toLowerCase();
  if (initialHash === "terms") {
    switchTab("terms");
  } else if (initialHash === "data-practices") {
    switchTab("data-practices");
  } else {
    switchTab("privacy");
  }

  // --- 2. Dynamic Table of Contents (TOC) Builder ---
  function buildTOC(activeTab) {
    if (!tocList) return;
    tocList.innerHTML = "";

    const activePane = document.getElementById(`pane-${activeTab}`);
    if (!activePane) return;

    const cards = activePane.querySelectorAll(".policy-card");
    if (tocTitle) {
      const titles = {
        "privacy": "Privacy Policy Contents",
        "terms": "Terms of Service Contents",
        "data-practices": "Data Practices Contents"
      };
      tocTitle.textContent = titles[activeTab] || "Table of Contents";
    }

    cards.forEach((card, index) => {
      const h2 = card.querySelector("h2");
      const secNum = card.querySelector(".section-number");
      if (!h2 || !card.id) return;

      const numStr = secNum ? secNum.textContent.trim() : String(index + 1).padStart(2, "0");
      const li = document.createElement("li");
      const a = document.createElement("a");
      a.href = `#${card.id}`;
      a.innerHTML = `<span class="toc-num">${numStr}</span> <span>${h2.textContent.trim()}</span>`;

      a.addEventListener("click", (e) => {
        e.preventDefault();
        const targetElement = document.getElementById(card.id);
        if (targetElement) {
          const yOffset = -90;
          const y = targetElement.getBoundingClientRect().top + window.pageYOffset + yOffset;
          window.scrollTo({ top: y, behavior: "smooth" });
          history.replaceState(null, null, `#${card.id}`);
        }
      });

      li.appendChild(a);
      tocList.appendChild(li);
    });

    updateScrollSpy();
  }

  // --- 3. ScrollSpy for TOC Active State ---
  function updateScrollSpy() {
    const activePane = document.querySelector(".doc-pane.active");
    if (!activePane || !tocList) return;

    const cards = activePane.querySelectorAll(".policy-card");
    const scrollPos = window.scrollY + 120;

    let currentCardId = "";
    cards.forEach(card => {
      const top = card.offsetTop;
      const height = card.offsetHeight;
      if (scrollPos >= top && scrollPos < top + height) {
        currentCardId = card.id;
      }
    });

    const tocLinks = tocList.querySelectorAll("a");
    tocLinks.forEach(link => {
      if (currentCardId && link.getAttribute("href") === `#${currentCardId}`) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });
  }

  window.addEventListener("scroll", updateScrollSpy, { passive: true });

  // --- 4. Live Search & Filtering ---
  function filterSections(query) {
    const q = query.trim().toLowerCase();
    const activePane = document.querySelector(".doc-pane.active");
    if (!activePane) return;

    const cards = activePane.querySelectorAll(".policy-card");
    let matchCount = 0;

    cards.forEach(card => {
      const text = card.textContent.toLowerCase();
      if (!q || text.includes(q)) {
        card.style.display = "";
        matchCount++;
      } else {
        card.style.display = "none";
      }
    });
  }

  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      filterSections(e.target.value);
    });
  }

  // --- 5. Copy Anchor Link + Toast Notification ---
  function showToast(msg) {
    if (!toast) return;
    if (toastMsg) toastMsg.textContent = msg || "Link copied to clipboard!";
    toast.classList.add("show");
    setTimeout(() => {
      toast.classList.remove("show");
    }, 2400);
  }

  document.addEventListener("click", (e) => {
    const anchorBtn = e.target.closest(".copy-anchor");
    if (!anchorBtn) return;

    const anchorId = anchorBtn.dataset.anchor;
    if (!anchorId) return;

    const url = `${window.location.origin}${window.location.pathname}#${anchorId}`;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(() => {
        showToast("Section link copied to clipboard!");
      }).catch(() => {
        prompt("Copy section link:", url);
      });
    } else {
      prompt("Copy section link:", url);
    }
  });

  // --- 6. GDPR Data Deletion Modal Controller ---
  function openModal() {
    if (dataModal) {
      dataModal.classList.add("open");
      document.body.style.overflow = "hidden";
    }
  }

  function closeModal() {
    if (dataModal) {
      dataModal.classList.remove("open");
      document.body.style.overflow = "";
    }
  }

  if (btnOpenDataModal) btnOpenDataModal.addEventListener("click", openModal);
  if (btnCloseDataModal) btnCloseDataModal.addEventListener("click", closeModal);
  if (btnCancelModal) btnCancelModal.addEventListener("click", closeModal);

  if (dataModal) {
    dataModal.addEventListener("click", (e) => {
      if (e.target === dataModal) closeModal();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && dataModal && dataModal.classList.contains("open")) {
      closeModal();
    }
  });
});
