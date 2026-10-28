/**
 * VoiceClaw Master Console Engine
 * Handles Discord session, server config, premium pricing control, and license management.
 */

document.addEventListener('DOMContentLoaded', async () => {
  // Elements
  const userProfileArea = document.getElementById('userProfileArea');
  const welcomeUser = document.getElementById('welcomeUser');
  const guildsGrid = document.getElementById('guildsGrid');
  const statGuildsCount = document.getElementById('statGuildsCount');
  const statPremiumCount = document.getElementById('statPremiumCount');
  const activeServersPill = document.getElementById('activeServersPill');
  const serverSearchInput = document.getElementById('serverSearchInput');

  // Tabs
  const navTabs = document.querySelectorAll('.dash-nav-tab[data-tab]');
  const tabContentServers = document.getElementById('tabContentServers');
  const tabContentPricing = document.getElementById('tabContentPricing');
  const tabContentLicenses = document.getElementById('tabContentLicenses');

  // Server Modal elements
  const guildModal = document.getElementById('guildModal');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const btnCancelConfig = document.getElementById('btnCancelConfig');
  const btnSaveConfig = document.getElementById('btnSaveConfig');
  const modalGuildIcon = document.getElementById('modalGuildIcon');
  const modalGuildName = document.getElementById('modalGuildName');
  const modalGuildId = document.getElementById('modalGuildId');
  const btnCopyGuildId = document.getElementById('btnCopyGuildId');
  const cfgRoomPrefix = document.getElementById('cfgRoomPrefix');
  const cfgUserLimit = document.getElementById('cfgUserLimit');
  const cfgBitrate = document.getElementById('cfgBitrate');
  const bitrateHintText = document.getElementById('bitrateHintText');
  const cfgAutoLock = document.getElementById('cfgAutoLock');
  const hubStatusText = document.getElementById('hubStatusText');

  // Pricing Elements
  const adminPricingGrid = document.getElementById('adminPricingGrid');
  const pricingCountPill = document.getElementById('pricingCountPill');
  const btnAddNewPlan = document.getElementById('btnAddNewPlan');
  const btnSavePaymentSettings = document.getElementById('btnSavePaymentSettings');
  const cfgCurrency = document.getElementById('cfgCurrency');
  const cfgCurrencySymbol = document.getElementById('cfgCurrencySymbol');
  const cfgSupportUrl = document.getElementById('cfgSupportUrl');
  const cfgPaymentInstructions = document.getElementById('cfgPaymentInstructions');

  // Plan Edit Modal
  const planModal = document.getElementById('planModal');
  const btnClosePlanModal = document.getElementById('btnClosePlanModal');
  const btnCancelPlanModal = document.getElementById('btnCancelPlanModal');
  const btnSavePlanModal = document.getElementById('btnSavePlanModal');
  const planModalTitle = document.getElementById('planModalTitle');
  const editPlanId = document.getElementById('editPlanId');
  const editPlanName = document.getElementById('editPlanName');
  const editPlanBadge = document.getElementById('editPlanBadge');
  const editPlanPrice = document.getElementById('editPlanPrice');
  const editPlanPeriod = document.getElementById('editPlanPeriod');
  const editPlanDesc = document.getElementById('editPlanDesc');
  const editPlanFeatures = document.getElementById('editPlanFeatures');
  const editPlanCheckoutUrl = document.getElementById('editPlanCheckoutUrl');
  const editPlanFeatured = document.getElementById('editPlanFeatured');
  const editPlanActive = document.getElementById('editPlanActive');

  // License Management Elements
  const grantTargetType = document.getElementById('grantTargetType');
  const grantServerSelect = document.getElementById('grantServerSelect');
  const grantTargetIdInput = document.getElementById('grantTargetIdInput');
  const grantPlanSelect = document.getElementById('grantPlanSelect');
  const btnSubmitGrantLicense = document.getElementById('btnSubmitGrantLicense');
  const tbodyPremGuilds = document.getElementById('tbodyPremGuilds');
  const tbodyPremUsers = document.getElementById('tbodyPremUsers');
  const premGuildCount = document.getElementById('premGuildCount');
  const premUserCount = document.getElementById('premUserCount');
  const licensesCountPill = document.getElementById('licensesCountPill');

  // Toast
  const dashToast = document.getElementById('dashToast');
  const dashToastMsg = document.getElementById('dashToastMsg');

  let currentGuilds = [];
  let selectedGuild = null;
  let currentPlans = [];

  function showToast(msg) {
    if (!dashToast) return;
    dashToastMsg.textContent = msg;
    dashToast.classList.add('show');
    setTimeout(() => {
      dashToast.classList.remove('show');
    }, 2800);
  }

  // 1. Tab Navigation Switcher
  navTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetTab = tab.getAttribute('data-tab');
      navTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      tabContentServers.classList.toggle('active', targetTab === 'servers');
      tabContentPricing.classList.toggle('active', targetTab === 'pricing');
      tabContentLicenses.classList.toggle('active', targetTab === 'licenses');

      if (targetTab === 'pricing') loadPricingData();
      if (targetTab === 'licenses') loadLicensesData();
    });
  });

  // Render User Profile Badge Helper
  function renderUserProfile(user) {
    if (!userProfileArea || !user) return;
    let avatarUrl = user.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';
    if (avatarUrl.includes('unsplash.com')) {
      avatarUrl = 'https://cdn.discordapp.com/avatars/1281114279948582923/6e876478cad012f7e56259015854b4bf.png?size=128';
    }
    const userName = (user.id === '1281114279948582923' || user.isOwner) ? 'darshonbro' : (user.username || user.global_name || 'Discord Admin');
    if (welcomeUser) welcomeUser.textContent = `Welcome back, ${userName}`;
    userProfileArea.innerHTML = `
      <div class="user-pill">
        <img src="${avatarUrl}" alt="${userName}" class="user-avatar" onerror="this.src='https://cdn.discordapp.com/embed/avatars/0.png'">
        <div class="user-info-text">
          <span class="user-name">${userName}</span>
          <span class="user-role-tag">${user.isOwner ? 'Bot Owner' : 'Server Admin'}</span>
        </div>
        <button id="btnLogout" class="user-logout-btn" title="Log Out">Exit</button>
      </div>
    `;
    const btnLogout = document.getElementById('btnLogout');
    if (btnLogout) {
      btnLogout.addEventListener('click', async () => {
        try {
          localStorage.removeItem('vc_cached_user');
          localStorage.removeItem('vc_cached_guilds');
        } catch(e) {}
        await fetch('/api/auth/logout', { method: 'POST' });
        window.location.href = '/';
      });
    }
  }

  // 1.5. Instant Cache-First Hydration (0ms Load Time - Never wait for spinner!)
  try {
    const cachedUser = JSON.parse(localStorage.getItem('vc_cached_user') || 'null');
    const cachedGuilds = JSON.parse(localStorage.getItem('vc_cached_guilds') || 'null');
    if (cachedUser && cachedUser.avatar_url && cachedUser.avatar_url.includes('unsplash.com')) {
      cachedUser.avatar_url = 'https://cdn.discordapp.com/avatars/1281114279948582923/6e876478cad012f7e56259015854b4bf.png?size=128';
      localStorage.setItem('vc_cached_user', JSON.stringify(cachedUser));
    }
    if (cachedUser && cachedGuilds && Array.isArray(cachedGuilds) && cachedGuilds.length > 0) {
      currentGuilds = cachedGuilds;
      renderUserProfile(cachedUser);
      renderGuilds(cachedGuilds);
      if (statGuildsCount) statGuildsCount.textContent = cachedGuilds.length;
      if (activeServersPill) activeServersPill.textContent = `${cachedGuilds.length} Active ${cachedGuilds.length === 1 ? 'Server' : 'Servers'}`;
      populateGrantServerDropdown(cachedGuilds);
    }
  } catch (e) {}

  // 2. Fetch Discord Session & Active Servers (Fast background revalidation)
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();

    if (!data.authenticated) {
      try {
        localStorage.removeItem('vc_cached_user');
        localStorage.removeItem('vc_cached_guilds');
      } catch(e) {}
      userProfileArea.innerHTML = `
        <a href="/api/auth/login" class="btn btn-primary" style="background:#5865F2; box-shadow: 0 0 16px rgba(88,101,242,0.35);">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.929 1.793 8.18 1.793 12.061 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.893.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.028zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/></svg>
          Authorize Discord
        </a>
      `;
      guildsGrid.innerHTML = `
        <div class="dash-loading-card" style="flex-direction:column; gap:16px;">
          <p>Please authorize Discord to view and manage your active VoiceClaw servers.</p>
          <a href="/api/auth/login" class="btn btn-primary" style="background:#5865F2;">Authorize Discord OAuth2</a>
        </div>
      `;
      return;
    }

    const user = data.user || {};
    currentGuilds = data.guilds || [];

    // Save to local cache so future visits are instantaneous
    try {
      localStorage.setItem('vc_cached_user', JSON.stringify(user));
      localStorage.setItem('vc_cached_guilds', JSON.stringify(currentGuilds));
    } catch(e) {}

    renderUserProfile(user);
    if (statGuildsCount) statGuildsCount.textContent = currentGuilds.length;
    if (activeServersPill) activeServersPill.textContent = `${currentGuilds.length} Active ${currentGuilds.length === 1 ? 'Server' : 'Servers'}`;

    renderGuilds(currentGuilds);
    populateGrantServerDropdown(currentGuilds);
    loadLicensesData(); // Background preload

  } catch (err) {
    console.error('Session error:', err);
    if (!currentGuilds || currentGuilds.length === 0) {
      guildsGrid.innerHTML = `<div class="dash-loading-card">Failed to communicate with VoiceClaw session API.</div>`;
    }
  }

  // 3. Render Guilds List
  function renderGuilds(guilds) {
    if (!guilds || guilds.length === 0) {
      guildsGrid.innerHTML = `
        <div class="dash-loading-card" style="flex-direction:column; gap:12px; text-align:center;">
          <div style="font-weight:700; color:#ffffff;">No Active VoiceClaw Servers Found</div>
          <p style="font-size:0.85rem; max-width:460px; color:var(--text-secondary);">
            No servers matching your criteria are currently joined by VoiceClaw.
          </p>
        </div>
      `;
      return;
    }

    guildsGrid.innerHTML = guilds.map(g => {
      const iconContent = g.icon_url
        ? `<img src="${g.icon_url}" class="guild-avatar" alt="${escapeHtml(g.name)}">`
        : `<div class="guild-avatar">${getInitials(g.name)}</div>`;

      return `
        <div class="guild-card" data-name="${g.name.toLowerCase()}" data-id="${g.id}">
          <div class="guild-top">
            <div class="guild-avatar-wrap">
              ${iconContent}
              <span class="guild-online-indicator" title="VoiceClaw Online"></span>
            </div>
            <div class="guild-meta">
              <div class="guild-name-row">
                <span class="guild-name" title="${escapeHtml(g.name)}">${escapeHtml(g.name)}</span>
              </div>
              <div class="guild-tags-row">
                <span class="guild-chip verified-bot">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  VoiceClaw Active
                </span>
                <span class="guild-chip">${g.membersFormatted || 'Connected Node'}</span>
              </div>
            </div>
          </div>
          <div class="guild-actions">
            <button class="btn-manage-server btn-manage" data-id="${g.id}">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
              Configure Voice Channels
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach click events to Manage buttons
    document.querySelectorAll('.btn-manage').forEach(btn => {
      btn.addEventListener('click', () => {
        const gId = btn.getAttribute('data-id');
        const g = currentGuilds.find(item => item.id === gId);
        if (g) openGuildModal(g);
      });
    });
  }

  // Populate Dropdown for License Grant
  function populateGrantServerDropdown(guilds) {
    if (!grantServerSelect) return;
    grantServerSelect.innerHTML = `<option value="">-- Choose from ${guilds.length} Active Servers --</option>` +
      guilds.map(g => `<option value="${g.id}">${escapeHtml(g.name)} (${g.id})</option>`).join('');

    grantServerSelect.addEventListener('change', (e) => {
      if (e.target.value) {
        grantTargetIdInput.value = e.target.value;
      }
    });
  }

  // 4. Server Search Filter
  if (serverSearchInput) {
    serverSearchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = currentGuilds.filter(g => 
        g.name.toLowerCase().includes(q) || (g.id && g.id.includes(q))
      );
      renderGuilds(filtered);
      if (activeServersPill) {
        activeServersPill.textContent = `${filtered.length} of ${currentGuilds.length} ${currentGuilds.length === 1 ? 'Server' : 'Servers'}`;
      }
    });
  }

  // =========================================================================
  // 5. CREATOR CHANNEL MODAL & GRANULAR FEATURE ROLES MATRIX

  // =========================================================================
  const creatorSubtabs = document.querySelectorAll('.creator-subtab[data-subtab]');
  const paneOverview = document.getElementById('paneOverview');
  const panePermissions = document.getElementById('panePermissions');
  const paneModeration = document.getElementById('paneModeration');
  const paneFeatures = document.getElementById('paneFeatures');
  const btnOpenToggleFeaturesTab = document.getElementById('btnOpenToggleFeaturesTab');

  const cfgUserLimitSlider = document.getElementById('cfgUserLimitSlider');
  const limitBadgeDisplay = document.getElementById('limitBadgeDisplay');
  const cfgCategory = document.getElementById('cfgCategory');
  const cfgPosition = document.getElementById('cfgPosition');
  const cfgAccessRole = document.getElementById('cfgAccessRole');
  const accessRoleBadge = document.getElementById('accessRoleBadge');
  const cfgPermissionsSync = document.getElementById('cfgPermissionsSync');
  const cfgPrivacyMode = document.getElementById('cfgPrivacyMode');
  
  // Owner Permissions DOM Elements
  const ownerPermsMultiselect = document.getElementById('ownerPermsMultiselect');
  const ownerPermsTrigger = document.getElementById('ownerPermsTrigger');
  const ownerPermsDropdown = document.getElementById('ownerPermsDropdown');
  const ownerPermsBadge = document.getElementById('ownerPermsBadge');
  const ownerPermsPreview = document.getElementById('ownerPermsPreview');
  const ownerPermsSearch = document.getElementById('ownerPermsSearch');
  const ownerPermsList = document.getElementById('ownerPermsList');
  const btnPermSelectAll = document.getElementById('btnPermSelectAll');
  const btnPermSelectSafe = document.getElementById('btnPermSelectSafe');
  const btnPermSelectNone = document.getElementById('btnPermSelectNone');

  // The 16 Permissions matching TempVoice & user screenshots exactly
  const OWNER_PERMISSIONS_DEF = [
    { id: "create_invite", name: "Create Invite", type: "amber", default: true },
    { id: "send_polls", name: "Send Polls", type: "green", default: true },
    { id: "send_voice_messages", name: "Send Voice Messages", type: "green", default: true },
    { id: "webcam_screenshare", name: "Webcam and Screenshare", type: "green", default: true },
    { id: "priority_speaker", name: "Priority Speaker", type: "amber", default: false },
    { id: "use_voice_activity", name: "Use Voice Activity", type: "green", default: true },
    { id: "set_voice_status", name: "Set Voice Channel Status", type: "green", default: true },
    { id: "use_soundboard", name: "Use Soundboard", type: "green", default: true },
    { id: "use_external_emoji", name: "Use External Emoji", type: "green", default: true },
    { id: "use_external_stickers", name: "Use External Stickers", type: "green", default: true },
    { id: "use_external_sounds", name: "Use External Sounds", type: "green", default: true },
    { id: "use_activities", name: "Use Activities", type: "green", default: true },
    { id: "manage_permissions", name: "Manage Permissions (Not Recommended)", type: "red", default: false },
    { id: "manage_channels", name: "Manage Channels", type: "red", default: false },
    { id: "delete_messages", name: "Delete Messages", type: "amber", default: false },
    { id: "disconnect_members", name: "Disconnect Members", type: "red", default: false }
  ];

  function getPermIconSvg(type) {
    if (type === 'green') {
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`;
    } else if (type === 'amber') {
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
    } else {
      return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;
    }
  }

  let selectedOwnerPerms = new Set();

  const cfgModerationWebhook = document.getElementById('cfgModerationWebhook');
  const cfgVoteKickSlider = document.getElementById('cfgVoteKickSlider');
  const voteKickBadge = document.getElementById('voteKickBadge');
  const cfgRecoverSettings = document.getElementById('cfgRecoverSettings');
  const cfgCensorNames = document.getElementById('cfgCensorNames');
  const cfgAgeRestriction = document.getElementById('cfgAgeRestriction');
  const modalPremiumBadge = document.getElementById('modalPremiumBadge');
  const featureRolesList = document.getElementById('featureRolesList');

  // Definition of the 19 granular features from Screenshots 4 & 5
  const FEATURE_DEFINITIONS = [
    { key: "inVoiceChat", name: "In-Voice Chat", cmd: "", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>` },
    { key: "voiceInvite", name: "Send an invite to a public chat", cmd: "/voice invite", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>` },
    { key: "voiceThread", name: "Creating Temporary Chat", cmd: "/voice thread", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>` },
    { key: "voiceWaiting", name: "Creating Waiting Rooms", cmd: "/voice waiting", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>` },
    { key: "lockInVoiceChat", name: "Locking only In-Voice Chat", cmd: "/voice privacy", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>` },
    { key: "lockChannel", name: "Locking Channel", cmd: "/voice privacy", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>` },
    { key: "hideChannel", name: "Hiding Channel", cmd: "/voice privacy", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>` },
    { key: "forceDelete", name: "Force Deleting Channel", cmd: "/voice delete", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>` },
    { key: "claimChannel", name: "Claiming Channels", cmd: "/voice claim", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/></svg>` },
    { key: "transferChannel", name: "Transferring Channels", cmd: "/voice transfer", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/></svg>` },
    { key: "kickUser", name: "Kicking/Disconnecting User", cmd: "/voice user kick", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/></svg>` },
    { key: "voteKick", name: "Starting Vote Kicks", cmd: "/voice user kick", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/></svg>` },
    { key: "inviteUser", name: "Inviting Users", cmd: "/voice user invite", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>` },
    { key: "trustBlock", name: "Trusting / Blocking Users", cmd: "/voice user trust & /voice user block", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>` },
    { key: "changeName", name: "Changing Channel Name", cmd: "/voice name", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>` },
    { key: "changeStatus", name: "Changing Channel Status", cmd: "/voice status", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="7" y2="18"/></svg>` },
    { key: "changeLimit", name: "Changing Channel User Limit", cmd: "/voice limit", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/></svg>` },
    { key: "changeRegion", name: "Changing Channel Region", cmd: "/voice region", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>` },
    { key: "changeBitrate", name: "Changing Channel Bitrate", cmd: "/voice bitrate", icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>` }
  ];

  function switchCreatorTab(tabName) {
    creatorSubtabs.forEach(tab => {
      tab.classList.toggle('active', tab.getAttribute('data-subtab') === tabName);
    });
    if (paneOverview) paneOverview.classList.toggle('active', tabName === 'overview');
    if (panePermissions) panePermissions.classList.toggle('active', tabName === 'permissions');
    if (paneModeration) paneModeration.classList.toggle('active', tabName === 'moderation');
    if (paneFeatures) paneFeatures.classList.toggle('active', tabName === 'features');
  }

  creatorSubtabs.forEach(tab => {
    tab.addEventListener('click', () => {
      switchCreatorTab(tab.getAttribute('data-subtab'));
    });
  });

  if (btnOpenToggleFeaturesTab) {
    btnOpenToggleFeaturesTab.addEventListener('click', () => {
      switchCreatorTab('features');
    });
  }

  // Sliders synchronization
  if (cfgUserLimitSlider && cfgUserLimit && limitBadgeDisplay) {
    cfgUserLimitSlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value) || 0;
      cfgUserLimit.value = val;
      limitBadgeDisplay.textContent = val === 0 ? '∞' : val;
    });

    cfgUserLimit.addEventListener('input', (e) => {
      const val = parseInt(e.target.value) || 0;
      cfgUserLimitSlider.value = val;
      limitBadgeDisplay.textContent = val === 0 ? '∞' : val;
    });
  }

  if (cfgVoteKickSlider && voteKickBadge) {
    cfgVoteKickSlider.addEventListener('input', (e) => {
      voteKickBadge.textContent = `${e.target.value}%`;
    });
  }

  if (cfgAccessRole && accessRoleBadge) {
    cfgAccessRole.addEventListener('change', (e) => {
      accessRoleBadge.textContent = e.target.options[e.target.selectedIndex]?.text || '@everyone';
    });
  }

  // =====================================================
  // OWNER PERMISSIONS INTERACTIVE CONTROLLER
  // =====================================================
  function updateOwnerPermsSummary() {
    const total = OWNER_PERMISSIONS_DEF.length;
    const count = selectedOwnerPerms.size;
    if (ownerPermsBadge) {
      if (count === 0) {
        ownerPermsBadge.textContent = "0 Selected";
      } else if (count === total) {
        ownerPermsBadge.textContent = `All ${total} Selected`;
      } else {
        ownerPermsBadge.textContent = `${count} of ${total} Selected`;
      }
    }
    if (ownerPermsPreview) {
      if (count === 0) {
        ownerPermsPreview.textContent = "No extra permissions granted";
      } else {
        const names = OWNER_PERMISSIONS_DEF
          .filter(p => selectedOwnerPerms.has(p.id))
          .map(p => p.name);
        if (names.length <= 2) {
          ownerPermsPreview.textContent = names.join(", ");
        } else {
          ownerPermsPreview.textContent = `${names.slice(0, 2).join(", ")}, +${names.length - 2} more`;
        }
      }
    }
  }

  function renderOwnerPermsList(filter = "") {
    if (!ownerPermsList) return;
    const term = filter.toLowerCase().trim();
    ownerPermsList.innerHTML = "";

    OWNER_PERMISSIONS_DEF.forEach(perm => {
      if (term && !perm.name.toLowerCase().includes(term)) return;
      const isChecked = selectedOwnerPerms.has(perm.id);

      const row = document.createElement('div');
      row.className = `perm-item-row ${isChecked ? 'selected' : ''}`;
      row.dataset.permId = perm.id;

      row.innerHTML = `
        <div class="perm-item-left">
          <span class="perm-icon perm-icon-${perm.type}">
            ${getPermIconSvg(perm.type)}
          </span>
          <span class="perm-item-title">${perm.name}</span>
        </div>
        <div class="perm-checkbox-custom ${isChecked ? 'checked' : ''}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
        </div>
      `;

      row.addEventListener('click', (e) => {
        e.stopPropagation();
        if (selectedOwnerPerms.has(perm.id)) {
          selectedOwnerPerms.delete(perm.id);
        } else {
          selectedOwnerPerms.add(perm.id);
        }
        const box = row.querySelector('.perm-checkbox-custom');
        const checkedNow = selectedOwnerPerms.has(perm.id);
        row.classList.toggle('selected', checkedNow);
        if (box) box.classList.toggle('checked', checkedNow);
        updateOwnerPermsSummary();
      });

      ownerPermsList.appendChild(row);
    });
  }

  function positionPermDropdown() {
    if (!ownerPermsDropdown || !ownerPermsTrigger) return;
    const triggerRect = ownerPermsTrigger.getBoundingClientRect();
    const modalRect = guildModal?.querySelector('.creator-modal-card')?.getBoundingClientRect();
    const bottomBound = modalRect ? modalRect.bottom : window.innerHeight;
    const spaceBelow = bottomBound - triggerRect.bottom;

    // If less than 300px below, drop UPWARDS so nothing is ever clipped!
    if (spaceBelow < 300) {
      ownerPermsMultiselect.classList.add('drop-up');
    } else {
      ownerPermsMultiselect.classList.remove('drop-up');
    }
  }

  if (ownerPermsTrigger) {
    ownerPermsTrigger.addEventListener('click', (e) => {
      e.stopPropagation();
      positionPermDropdown();
      const isOpen = ownerPermsMultiselect.classList.toggle('open');
      if (isOpen) {
        positionPermDropdown();
        if (ownerPermsSearch) {
          ownerPermsSearch.value = "";
          renderOwnerPermsList();
          setTimeout(() => ownerPermsSearch.focus(), 60);
        }
      }
    });
  }

  if (ownerPermsSearch) {
    ownerPermsSearch.addEventListener('input', (e) => {
      renderOwnerPermsList(e.target.value);
    });
    ownerPermsSearch.addEventListener('click', (e) => e.stopPropagation());
  }

  if (btnPermSelectAll) {
    btnPermSelectAll.addEventListener('click', (e) => {
      e.stopPropagation();
      OWNER_PERMISSIONS_DEF.forEach(p => selectedOwnerPerms.add(p.id));
      renderOwnerPermsList(ownerPermsSearch?.value || "");
      updateOwnerPermsSummary();
    });
  }

  if (btnPermSelectSafe) {
    btnPermSelectSafe.addEventListener('click', (e) => {
      e.stopPropagation();
      selectedOwnerPerms.clear();
      OWNER_PERMISSIONS_DEF.forEach(p => {
        if (p.default) selectedOwnerPerms.add(p.id);
      });
      renderOwnerPermsList(ownerPermsSearch?.value || "");
      updateOwnerPermsSummary();
    });
  }

  if (btnPermSelectNone) {
    btnPermSelectNone.addEventListener('click', (e) => {
      e.stopPropagation();
      selectedOwnerPerms.clear();
      renderOwnerPermsList(ownerPermsSearch?.value || "");
      updateOwnerPermsSummary();
    });
  }

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    if (ownerPermsMultiselect && !ownerPermsMultiselect.contains(e.target)) {
      ownerPermsMultiselect.classList.remove('open');
    }
  });

  window.addEventListener('resize', () => {
    if (ownerPermsMultiselect && ownerPermsMultiselect.classList.contains('open')) {
      positionPermDropdown();
    }
  });
  let currentRolePowers = {};
  let currentServerRoles = [];





  // Modal open function
  async function openGuildModal(guild) {
    selectedGuild = guild;
    modalGuildName.textContent = guild.name || "Creator Channel";
    switchCreatorTab('overview');

    // Instant UI feedback: Open the modal immediately
    guildModal.classList.add('open');

    // Set immediate defaults & lazy loading placeholders so fields are NEVER empty
    if (cfgRoomPrefix) cfgRoomPrefix.value = "[OWNER_NICKNAME]'s Channel";
    if (cfgUserLimit) cfgUserLimit.value = 0;
    if (cfgUserLimitSlider) cfgUserLimitSlider.value = 0;
    if (limitBadgeDisplay) limitBadgeDisplay.textContent = '∞';
    if (cfgVoteKickSlider) cfgVoteKickSlider.value = 50;
    if (voteKickBadge) voteKickBadge.textContent = '50%';
    if (cfgBitrate) cfgBitrate.value = "64";
    if (cfgPosition) cfgPosition.value = "bottom";
    if (cfgPermissionsSync) cfgPermissionsSync.value = "dont_sync";
    if (cfgPrivacyMode) cfgPrivacyMode.value = "public";
    selectedOwnerPerms.clear();
    OWNER_PERMISSIONS_DEF.forEach(p => {
      if (p.default) selectedOwnerPerms.add(p.id);
    });
    renderOwnerPermsList();
    updateOwnerPermsSummary();
    if (cfgRecoverSettings) cfgRecoverSettings.value = "all";

    // Immediate fallback options so dropdowns never appear blank
    if (cfgCategory && cfgCategory.options.length <= 1) {
      cfgCategory.innerHTML = `<option value="">Default (Synced with Bot Category)</option>`;
    }
    if (cfgAccessRole && cfgAccessRole.options.length <= 1) {
      cfgAccessRole.innerHTML = `<option value="@everyone" selected>@everyone</option>`;
      if (accessRoleBadge) accessRoleBadge.textContent = "@everyone";
    }

    function applyConfigToModal(data) {
      if (!data) return;

      // Update Premium badge
      if (modalPremiumBadge) {
        if (data.isPremium) {
          modalPremiumBadge.className = 'creator-badge premium-active';
          modalPremiumBadge.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px; vertical-align:-1px;"><path d="M2 4l3 12h14l3-12-6 7-4-7-4 7-6-7zm3 16h14v2H5v-2z"/></svg> Pro Premium';
        } else {
          modalPremiumBadge.className = 'creator-badge';
          modalPremiumBadge.innerHTML = 'No Premium';
        }
      }

      // Populate Categories
      if (cfgCategory) {
        const catList = data.categories || [];
        cfgCategory.innerHTML = `<option value="">Default (Synced with Bot Category)</option>` +
          catList.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('');
        if (data.categoryID) cfgCategory.value = data.categoryID;
      }

      // Populate Access Roles
      const rolesList = (data.roles && data.roles.length > 0) ? data.roles : [{ id: "@everyone", name: "@everyone" }];
      if (cfgAccessRole) {
        cfgAccessRole.innerHTML = rolesList.map(r => `<option value="${r.id}">${escapeHtml(r.name)}</option>`).join('');
        const savedAccess = (data.accessRoles && data.accessRoles[0]) || "@everyone";
        cfgAccessRole.value = savedAccess;
        if (!cfgAccessRole.value && rolesList.length > 0) {
          cfgAccessRole.value = rolesList[0].id;
        }
        if (accessRoleBadge) {
          const selectedText = cfgAccessRole.options[cfgAccessRole.selectedIndex]?.text || '@everyone';
          accessRoleBadge.textContent = selectedText;
        }
      }

      // Overview settings
      if (cfgRoomPrefix && data.roomPrefix !== undefined) cfgRoomPrefix.value = data.roomPrefix;
      const uLimit = data.userLimit !== undefined ? data.userLimit : 0;
      if (cfgUserLimit) cfgUserLimit.value = uLimit;
      if (cfgUserLimitSlider) cfgUserLimitSlider.value = uLimit;
      if (limitBadgeDisplay) limitBadgeDisplay.textContent = uLimit === 0 ? '∞' : uLimit;
      if (cfgBitrate && data.bitrate !== undefined) cfgBitrate.value = String(data.bitrate);
      if (cfgPosition && data.position !== undefined) cfgPosition.value = data.position;

      // Permissions settings
      if (cfgPermissionsSync && data.permissionsSync !== undefined) cfgPermissionsSync.value = data.permissionsSync;
      if (cfgPrivacyMode && data.privacyMode !== undefined) cfgPrivacyMode.value = data.privacyMode;

      // Populate Owner Permissions (16 items)
      selectedOwnerPerms.clear();
      if (data.ownerPermissions && Array.isArray(data.ownerPermissions) && data.ownerPermissions.length > 0) {
        const raw = data.ownerPermissions.join(' ');
        if (raw === "standard" || (raw.includes("manage_channel") && !raw.includes("send_polls"))) {
          OWNER_PERMISSIONS_DEF.forEach(p => {
            if (p.default || p.id === "manage_channels" || p.id === "disconnect_members") {
              selectedOwnerPerms.add(p.id);
            }
          });
        } else if (raw === "all" || raw.includes("administrator")) {
          OWNER_PERMISSIONS_DEF.forEach(p => selectedOwnerPerms.add(p.id));
        } else if (raw === "minimal") {
          selectedOwnerPerms.add("use_voice_activity");
        } else {
          data.ownerPermissions.forEach(p => {
            if (p === "manage_channel") selectedOwnerPerms.add("manage_channels");
            else if (p === "move_members") selectedOwnerPerms.add("disconnect_members");
            else selectedOwnerPerms.add(p);
          });
        }
      } else {
        OWNER_PERMISSIONS_DEF.forEach(p => {
          if (p.default) selectedOwnerPerms.add(p.id);
        });
      }
      renderOwnerPermsList();
      updateOwnerPermsSummary();

      // Moderation settings
      if (cfgModerationWebhook && data.moderationWebhook !== undefined) cfgModerationWebhook.value = data.moderationWebhook;
      const vkPct = data.voteKickPercentage || 50;
      if (cfgVoteKickSlider) cfgVoteKickSlider.value = vkPct;
      if (voteKickBadge) voteKickBadge.textContent = `${vkPct}%`;
      if (cfgRecoverSettings && data.recoverSettings !== undefined) cfgRecoverSettings.value = data.recoverSettings;
      if (cfgCensorNames && data.censorChannelNames !== undefined) cfgCensorNames.value = data.censorChannelNames;
      if (cfgAgeRestriction && data.ageRestriction !== undefined) cfgAgeRestriction.checked = !!data.ageRestriction;

      // Populate Toggle Features Matrix (19 items with role dropdowns)
      if (featureRolesList) {
        const savedFeatureRoles = data.featureRoles || {};
        featureRolesList.innerHTML = FEATURE_DEFINITIONS.map(feat => {
          const savedRole = savedFeatureRoles[feat.key] || "@everyone";
          const optionsHtml = rolesList.map(r => `
            <option value="${r.id}" ${r.id === savedRole ? 'selected' : ''}>${escapeHtml(r.name)}</option>
          `).join('');

          return `
            <div class="feature-role-item" data-feature="${feat.key}">
              <div class="feature-info-col">
                <div class="feature-icon-box">
                  ${feat.icon}
                </div>
                <div class="feature-name-group">
                  <span class="feature-name">${escapeHtml(feat.name)}</span>
                  ${feat.cmd ? `<span class="feature-cmd">${escapeHtml(feat.cmd)}</span>` : ''}
                </div>
              </div>
              <div class="feature-action-col">
                <select class="feature-role-select" data-feature-key="${feat.key}">
                  ${optionsHtml}
                </select>
              </div>
            </div>
          `;
        }).join('');
      }

      currentServerRoles = rolesList;
      currentRolePowers = (data.rolePowers && typeof data.rolePowers === 'object') ? JSON.parse(JSON.stringify(data.rolePowers)) : {};

      // Convert all selects in modal into sleek custom Discord dropdowns
      if (typeof window.refreshCustomSelects === 'function') {
        window.refreshCustomSelects();
      }
    }

    // 1. Instant local cached configuration (0ms delay)
    const cfgCacheKey = `vc_cfg_${guild.id}`;
    try {
      const cachedData = JSON.parse(localStorage.getItem(cfgCacheKey) || 'null');
      if (cachedData) {
        applyConfigToModal(cachedData);
      }
    } catch(e) {}

    // 2. Fetch fresh config from backend and update smoothly
    try {
      const res = await fetch(`/api/guild/${guild.id}`);
      const data = await res.json();
      try {
        localStorage.setItem(cfgCacheKey, JSON.stringify(data));
      } catch(e) {}
      applyConfigToModal(data);
    } catch (err) {
      console.error('Error fetching guild settings:', err);
    }

    guildModal.classList.add('open');
  }


  function closeGuildModal() {
    guildModal.classList.remove('open');
    selectedGuild = null;
  }

  btnCloseModal.addEventListener('click', closeGuildModal);
  btnCancelConfig.addEventListener('click', closeGuildModal);
  guildModal.addEventListener('click', (e) => {
    if (e.target === guildModal) closeGuildModal();
  });

  // Dynamic Variable Chips
  document.querySelectorAll('.var-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const tag = chip.getAttribute('data-var');
      if (tag && cfgRoomPrefix) {
        cfgRoomPrefix.value = (cfgRoomPrefix.value + ' ' + tag).trim();
        cfgRoomPrefix.focus();
      }
    });
  });

  // Save Guild Config (Including Granular Feature Roles)
  btnSaveConfig.addEventListener('click', async () => {
    if (!selectedGuild) return;
    btnSaveConfig.disabled = true;
    btnSaveConfig.innerHTML = `<span class="dash-spinner" style="width:14px;height:14px;border-width:2px;"></span> Saving...`;

    // Collect all 19 feature role mappings
    const featureRolesPayload = {};
    document.querySelectorAll('.feature-role-select').forEach(sel => {
      const key = sel.getAttribute('data-feature-key');
      if (key) {
        featureRolesPayload[key] = sel.value;
      }
    });

    const payload = {
      roomPrefix: cfgRoomPrefix.value.trim() || "[OWNER_NICKNAME]'s Channel",
      categoryID: cfgCategory.value || "",
      userLimit: parseInt(cfgUserLimit.value) || 0,
      bitrate: parseInt(cfgBitrate.value) || 64,
      position: cfgPosition.value || "bottom",
      accessRoles: [cfgAccessRole.value || "@everyone"],
      privacyMode: cfgPrivacyMode.value || "public",
      permissionsSync: cfgPermissionsSync.value || "dont_sync",
      ownerPermissions: Array.from(selectedOwnerPerms),
      moderationWebhook: cfgModerationWebhook.value.trim(),
      voteKickPercentage: parseInt(cfgVoteKickSlider.value) || 50,
      recoverSettings: cfgRecoverSettings.value || "all",
      censorChannelNames: cfgCensorNames.value.trim(),
      ageRestriction: cfgAgeRestriction.checked,
      featureRoles: featureRolesPayload,
      rolePowers: currentRolePowers
    };

    try {
      const res = await fetch(`/api/guild/${selectedGuild.id}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        showToast(`Configuration updated for ${selectedGuild.name}`);
        closeGuildModal();
      } else {
        showToast('Error saving settings: ' + (data.error || 'Server error'));
      }
    } catch (err) {
      showToast('Network error while saving settings');
    } finally {
      btnSaveConfig.disabled = false;
      btnSaveConfig.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
        Save All Settings
      `;
    }
  });


  // =========================================================================
  // 6. PREMIUM PRICING CONTROL ENGINE
  // =========================================================================
  async function loadPricingData() {
    try {
      adminPricingGrid.innerHTML = `
        <div class="dash-loading-card">
          <div class="dash-spinner"></div>
          <span>Loading pricing tiers...</span>
        </div>
      `;

      const res = await fetch('/api/admin/pricing');
      const data = await res.json();
      currentPlans = data.plans || [];
      const settings = data.settings || {};

      if (pricingCountPill) {
        pricingCountPill.textContent = `${currentPlans.length} Active Tiers`;
      }

      if (cfgCurrency && settings.currency) cfgCurrency.value = settings.currency;
      if (cfgCurrencySymbol && settings.currencySymbol) cfgCurrencySymbol.value = settings.currencySymbol;
      if (cfgSupportUrl && settings.supportDiscord) cfgSupportUrl.value = settings.supportDiscord;
      if (cfgPaymentInstructions && settings.paymentInstructions) cfgPaymentInstructions.value = settings.paymentInstructions;

      renderAdminPricingCards(currentPlans);

    } catch (err) {
      console.error('Pricing load error:', err);
      adminPricingGrid.innerHTML = `<div class="dash-loading-card">Failed to load pricing plans.</div>`;
    }
  }

  function renderAdminPricingCards(plans) {
    if (!plans || plans.length === 0) {
      adminPricingGrid.innerHTML = `
        <div class="dash-loading-card" style="grid-column: 1 / -1; flex-direction:column; gap:12px;">
          <p>No pricing plans configured yet.</p>
          <button class="btn btn-primary" id="btnSeedDefaultPlans">Initialize Standard Plans</button>
        </div>
      `;
      document.getElementById('btnSeedDefaultPlans')?.addEventListener('click', () => loadPricingData());
      return;
    }

    adminPricingGrid.innerHTML = plans.map(p => {
      const badgeHtml = p.badge ? `<span class="pricing-card-badge">${escapeHtml(p.badge)}</span>` : '';
      const featuresHtml = (p.features || []).map(f => `
        <li class="pricing-feature-item">
          <svg class="feature-check-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
          <span>${escapeHtml(f)}</span>
        </li>
      `).join('');

      return `
        <div class="pricing-admin-card ${p.isFeatured ? 'featured' : ''}">
          <div>
            ${badgeHtml}
            <h3 class="pricing-plan-title">${escapeHtml(p.name)}</h3>
            <p class="pricing-plan-desc">${escapeHtml(p.description || '')}</p>
            
            <div class="pricing-price-row">
              <span class="pricing-price-val">${escapeHtml(p.price)}</span>
              <span class="pricing-price-period">${escapeHtml(p.period || '')}</span>
            </div>

            <ul class="pricing-features-list">
              ${featuresHtml}
            </ul>
          </div>

          <div class="pricing-card-actions">
            <button class="btn btn-secondary btn-edit-plan" data-id="${p.id}" style="flex:1;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              Edit Tier
            </button>
            <button class="btn btn-secondary btn-delete-plan" data-id="${p.id}" style="color:#f87171;" title="Delete Plan">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach click events
    document.querySelectorAll('.btn-edit-plan').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        const plan = currentPlans.find(p => p.id === id);
        if (plan) openPlanModal(plan);
      });
    });

    document.querySelectorAll('.btn-delete-plan').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        if (!confirm('Are you sure you want to delete this pricing tier?')) return;
        try {
          const res = await fetch('/api/admin/pricing/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
          });
          const d = await res.json();
          if (d.success) {
            showToast('Pricing plan deleted');
            loadPricingData();
          }
        } catch (e) {
          showToast('Failed to delete plan');
        }
      });
    });
  }

  // Save Global Payment Settings
  if (btnSavePaymentSettings) {
    btnSavePaymentSettings.addEventListener('click', async () => {
      btnSavePaymentSettings.disabled = true;
      btnSavePaymentSettings.textContent = 'Saving...';

      const payload = {
        plans: currentPlans,
        settings: {
          currency: cfgCurrency.value.trim() || 'USD',
          currencySymbol: cfgCurrencySymbol.value.trim() || '$',
          supportDiscord: cfgSupportUrl.value.trim() || 'https://discord.gg/y9pgpbt',
          paymentInstructions: cfgPaymentInstructions.value.trim()
        }
      };

      try {
        const res = await fetch('/api/admin/pricing/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await res.json();
        if (d.success) {
          showToast('Payment settings saved successfully');
        } else {
          showToast('Failed to save settings: ' + (d.error || 'Server error'));
        }
      } catch (e) {
        showToast('Network error while saving settings');
      } finally {
        btnSavePaymentSettings.disabled = false;
        btnSavePaymentSettings.textContent = 'Save Settings';
      }
    });
  }

  // Plan Edit Modal
  function openPlanModal(plan = null) {
    if (plan) {
      planModalTitle.textContent = `Edit Plan: ${plan.name}`;
      editPlanId.value = plan.id;
      editPlanName.value = plan.name;
      editPlanBadge.value = plan.badge || '';
      editPlanPrice.value = plan.price;
      editPlanPeriod.value = plan.period || '';
      editPlanDesc.value = plan.description || '';
      editPlanFeatures.value = (plan.features || []).join('\n');
      editPlanCheckoutUrl.value = plan.checkoutUrl || 'https://discord.gg/y9pgpbt';
      editPlanFeatured.checked = !!plan.isFeatured;
      editPlanActive.checked = plan.active !== false;
    } else {
      planModalTitle.textContent = 'Create New Pricing Tier';
      editPlanId.value = 'plan_' + Date.now();
      editPlanName.value = '';
      editPlanBadge.value = '';
      editPlanPrice.value = '$4.99';
      editPlanPeriod.value = '/ month';
      editPlanDesc.value = '';
      editPlanFeatures.value = '1 Discord Server Activation\n384 kbps Crystal Audio\nUnlimited Voice Hubs';
      editPlanCheckoutUrl.value = 'https://discord.gg/y9pgpbt';
      editPlanFeatured.checked = false;
      editPlanActive.checked = true;
    }
    planModal.classList.add('open');
  }

  function closePlanModal() {
    planModal.classList.remove('open');
  }

  if (btnAddNewPlan) btnAddNewPlan.addEventListener('click', () => openPlanModal(null));
  if (btnClosePlanModal) btnClosePlanModal.addEventListener('click', closePlanModal);
  if (btnCancelPlanModal) btnCancelPlanModal.addEventListener('click', closePlanModal);
  if (planModal) planModal.addEventListener('click', (e) => {
    if (e.target === planModal) closePlanModal();
  });

  // Save Plan from Modal
  if (btnSavePlanModal) {
    btnSavePlanModal.addEventListener('click', async () => {
      const pId = editPlanId.value.trim();
      const pName = editPlanName.value.trim();
      const pPrice = editPlanPrice.value.trim();

      if (!pName || !pPrice) {
        alert('Please specify both plan name and price.');
        return;
      }

      const featuresArr = editPlanFeatures.value
        .split('\n')
        .map(f => f.trim())
        .filter(f => f.length > 0);

      const planObj = {
        id: pId,
        name: pName,
        badge: editPlanBadge.value.trim(),
        price: pPrice,
        period: editPlanPeriod.value.trim(),
        description: editPlanDesc.value.trim(),
        features: featuresArr,
        checkoutUrl: editPlanCheckoutUrl.value.trim(),
        isFeatured: editPlanFeatured.checked,
        active: editPlanActive.checked
      };

      // Upsert into currentPlans
      const existingIdx = currentPlans.findIndex(p => p.id === pId);
      if (existingIdx >= 0) {
        currentPlans[existingIdx] = planObj;
      } else {
        currentPlans.push(planObj);
      }

      btnSavePlanModal.disabled = true;
      btnSavePlanModal.textContent = 'Saving...';

      try {
        const res = await fetch('/api/admin/pricing/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ plans: currentPlans })
        });
        const d = await res.json();
        if (d.success) {
          showToast(`Saved tier: ${pName}`);
          closePlanModal();
          loadPricingData();
        } else {
          showToast('Error saving plan: ' + (d.error || 'Server error'));
        }
      } catch (e) {
        showToast('Network error while saving plan');
      } finally {
        btnSavePlanModal.disabled = false;
        btnSavePlanModal.textContent = 'Save Tier';
      }
    });
  }

  // =========================================================================
  // 7. GRANTED LICENSES MANAGEMENT ENGINE
  // =========================================================================
  async function loadLicensesData() {
    try {
      const res = await fetch('/api/admin/premium/list');
      const data = await res.json();

      const premGuilds = data.premiumGuilds || [];
      const premUsers = data.premiumUsers || [];

      if (statPremiumCount) statPremiumCount.textContent = `${premGuilds.length + premUsers.length} VIP`;
      if (premGuildCount) premGuildCount.textContent = `${premGuilds.length} Guilds`;
      if (premUserCount) premUserCount.textContent = `${premUsers.length} Users`;
      if (licensesCountPill) licensesCountPill.textContent = `${premGuilds.length + premUsers.length} Active Licenses`;

      // Render Guilds Table
      if (premGuilds.length === 0) {
        tbodyPremGuilds.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:20px;">No premium guilds registered.</td></tr>`;
      } else {
        tbodyPremGuilds.innerHTML = premGuilds.map(g => {
          const matchedGuild = currentGuilds.find(cg => cg.id === g.guildID);
          const nameDisplay = matchedGuild ? escapeHtml(matchedGuild.name) : `Guild ${g.guildID}`;
          return `
            <tr>
              <td>
                <div style="font-weight:700; color:#fff;">${nameDisplay}</div>
                <div style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">${g.guildID}</div>
              </td>
              <td><span class="guild-chip verified-bot">${escapeHtml(g.plan || 'Lifetime')}</span></td>
              <td style="font-size:0.75rem;">${g.addedAt || 'Permanent'}</td>
              <td>
                <button class="btn-revoke btn-revoke-license" data-type="guild" data-id="${g.guildID}">Revoke</button>
              </td>
            </tr>
          `;
        }).join('');
      }

      // Render Users Table
      if (premUsers.length === 0) {
        tbodyPremUsers.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted); padding:20px;">No premium users registered.</td></tr>`;
      } else {
        tbodyPremUsers.innerHTML = premUsers.map(u => {
          return `
            <tr>
              <td>
                <div style="font-weight:700; color:#fff;">User VIP</div>
                <div style="font-size:0.7rem; color:var(--text-muted); font-family:var(--font-mono);">${u.userID}</div>
              </td>
              <td><span class="guild-chip verified-bot">${escapeHtml(u.plan || 'Lifetime')}</span></td>
              <td style="font-size:0.75rem;">${u.addedAt || 'Permanent'}</td>
              <td>
                <button class="btn-revoke btn-revoke-license" data-type="user" data-id="${u.userID}">Revoke</button>
              </td>
            </tr>
          `;
        }).join('');
      }

      // Attach Revoke handlers
      document.querySelectorAll('.btn-revoke-license').forEach(btn => {
        btn.addEventListener('click', async () => {
          const type = btn.getAttribute('data-type');
          const id = btn.getAttribute('data-id');
          if (!confirm(`Are you sure you want to revoke premium from ${type} ${id}?`)) return;

          try {
            const r = await fetch('/api/admin/premium/revoke', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ targetType: type, targetID: id })
            });
            const d = await r.json();
            if (d.success) {
              showToast(`Revoked premium from ${id}`);
              loadLicensesData();
            }
          } catch (e) {
            showToast('Failed to revoke license');
          }
        });
      });

    } catch (err) {
      console.error('License load error:', err);
    }
  }

  // Grant New License Submit
  if (btnSubmitGrantLicense) {
    btnSubmitGrantLicense.addEventListener('click', async () => {
      const type = grantTargetType.value;
      const targetId = grantTargetIdInput.value.trim();
      const plan = grantPlanSelect.value;

      if (!targetId) {
        alert('Please specify a Discord Guild ID or User ID.');
        return;
      }

      btnSubmitGrantLicense.disabled = true;
      btnSubmitGrantLicense.textContent = 'Granting...';

      try {
        const res = await fetch('/api/admin/premium/grant', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            targetType: type,
            targetID: targetId,
            plan: plan
          })
        });
        const d = await res.json();
        if (d.success) {
          showToast(`Granted ${plan} premium to ${targetId}!`);
          grantTargetIdInput.value = '';
          loadLicensesData();
        } else {
          showToast('Error granting license: ' + (d.error || 'Server error'));
        }
      } catch (e) {
        showToast('Network error while granting license');
      } finally {
        btnSubmitGrantLicense.disabled = false;
        btnSubmitGrantLicense.textContent = 'Grant License';
      }
    });
  }

  // Helpers
  function getInitials(name) {
    if (!name) return 'VC';
    return name.split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // =========================================================================
  // Beautiful Custom Discord Dropdown Enhancer (Replaces ugly browser selects)
  // =========================================================================
  function enhanceCustomSelect(selectEl) {
    if (!selectEl || selectEl.dataset.enhanced === 'true') return;
    selectEl.dataset.enhanced = 'true';
    selectEl.style.display = 'none';

    const wrapper = document.createElement('div');
    wrapper.className = 'dash-custom-select';

    const trigger = document.createElement('div');
    trigger.className = 'dash-custom-trigger';
    
    const triggerText = document.createElement('span');
    triggerText.className = 'trigger-text';
    const selectedOption = selectEl.options[selectEl.selectedIndex] || selectEl.options[0];
    triggerText.textContent = selectedOption ? selectedOption.text : 'Select...';

    const chevron = document.createElement('div');
    chevron.className = 'trigger-chevron';
    chevron.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>`;

    trigger.appendChild(triggerText);
    trigger.appendChild(chevron);

    const optionsContainer = document.createElement('div');
    optionsContainer.className = 'dash-custom-options';

    function buildOptions() {
      optionsContainer.innerHTML = '';
      Array.from(selectEl.options).forEach(opt => {
        const item = document.createElement('div');
        item.className = 'dash-custom-option' + (opt.value === selectEl.value ? ' selected' : '');
        item.textContent = opt.text;
        item.setAttribute('data-value', opt.value);

        item.addEventListener('click', (e) => {
          e.stopPropagation();
          selectEl.value = opt.value;
          triggerText.textContent = opt.text;
          wrapper.classList.remove('active');
          selectEl.dispatchEvent(new Event('change', { bubbles: true }));
          buildOptions();
        });

        optionsContainer.appendChild(item);
      });
    }

    buildOptions();

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const isActive = wrapper.classList.contains('active');
      document.querySelectorAll('.dash-custom-select.active').forEach(w => w.classList.remove('active'));
      if (!isActive) {
        buildOptions();
        wrapper.classList.add('active');
      }
    });

    // Sync if selectEl value is changed programmatically
    selectEl.addEventListener('update-ui', () => {
      const cur = selectEl.options[selectEl.selectedIndex];
      if (cur) triggerText.textContent = cur.text;
      buildOptions();
    });

    wrapper.appendChild(trigger);
    wrapper.appendChild(optionsContainer);
    selectEl.parentNode.insertBefore(wrapper, selectEl.nextSibling);
  }

  // Auto-enhance modal dropdowns
  window.refreshCustomSelects = () => {
    document.querySelectorAll('.creator-modal-card select.dash-select, .feature-role-select').forEach(sel => {
      enhanceCustomSelect(sel);
      sel.dispatchEvent(new Event('update-ui'));
    });
  };

  // Close all custom dropdowns when clicking outside
  document.addEventListener('click', () => {
    document.querySelectorAll('.dash-custom-select.active').forEach(w => w.classList.remove('active'));
  });

});

