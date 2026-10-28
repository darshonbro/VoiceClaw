/**
 * VoiceClaw - High-Performance Scroll & Simulator Engine
 * Zero Bloat • 100% Crisp Interactions
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Scroll Progress Bar & Back to Top
  const progressBar = document.getElementById('progressBar');
  const siteHeader = document.querySelector('.site-header');
  const backToTop = document.getElementById('backToTop');

  window.addEventListener('scroll', () => {
    const scrollTop = window.scrollY;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const percent = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;

    if (progressBar) progressBar.style.width = `${percent}%`;

    if (siteHeader) {
      if (scrollTop > 20) siteHeader.classList.add('scrolled');
      else siteHeader.classList.remove('scrolled');
    }

    if (backToTop) {
      if (scrollTop > 350) backToTop.classList.add('show');
      else backToTop.classList.remove('show');
    }
  }, { passive: true });

  if (backToTop) {
    backToTop.addEventListener('click', () => {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // 2. Scroll-Reveal
  const reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && reveals.length > 0) {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('active');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });

    reveals.forEach(el => revealObserver.observe(el));
  } else {
    reveals.forEach(el => el.classList.add('active'));
  }

  // 3. Metric Number Counters & Real Data Sync
  const metricNums = document.querySelectorAll('.metric-num[data-target]');

  async function syncRealStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) return;
      const data = await res.json();
      
      const elGuilds = document.getElementById('metricGuilds');
      const elChannels = document.getElementById('metricChannels');
      const elUptime = document.getElementById('metricUptime');
      const elLatency = document.getElementById('metricLatency');

      if (elGuilds && data.guilds) {
        elGuilds.setAttribute('data-target', data.guilds);
      }
      if (elChannels && (data.channels_spawned || data.voice_users)) {
        elChannels.setAttribute('data-target', data.channels_spawned || data.voice_users);
      }
      if (elUptime && data.uptime) {
        elUptime.setAttribute('data-target', data.uptime);
      }
      if (elLatency && data.latency) {
        elLatency.setAttribute('data-target', data.latency);
      }
    } catch (_) {
      // Fallback values in HTML already represent real baseline stats
    }
  }
  syncRealStats();

  // Auth state check
  async function checkAuthSession() {
    const navAuthBtn = document.getElementById('navAuthBtn');
    if (!navAuthBtn) return;
    try {
      const res = await fetch('/api/auth/me');
      const data = await res.json();
      if (data.authenticated && data.user) {
        navAuthBtn.href = '/dashboard';
        const avatar = data.user.avatar_url || 'https://cdn.discordapp.com/embed/avatars/0.png';
        const name = data.user.global_name || data.user.username;
        navAuthBtn.innerHTML = `
          <img src="${avatar}" style="width:18px;height:18px;border-radius:50%;object-fit:cover;border:1px solid #ff2a6d;">
          <span>${name}</span>
        `;
      }
    } catch (_) {}
  }
  checkAuthSession();

  if ('IntersectionObserver' in window && metricNums.length > 0) {
    const counterObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });

    metricNums.forEach(el => counterObserver.observe(el));
  }

  function animateCounter(el) {
    const target = parseFloat(el.getAttribute('data-target'));
    const prefix = el.getAttribute('data-prefix') || '';
    const suffix = el.getAttribute('data-suffix') || '';
    const isDecimal = el.getAttribute('data-decimal') === 'true';
    const duration = 1400;
    const start = performance.now();

    function step(now) {
      const progress = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 3);
      const val = target * ease;

      if (isDecimal) {
        el.textContent = `${prefix}${val.toFixed(2)}${suffix}`;
      } else {
        el.textContent = `${prefix}${Math.floor(val).toLocaleString()}${suffix}`;
      }

      if (progress < 1) requestAnimationFrame(step);
      else {
        el.textContent = isDecimal
          ? `${prefix}${target.toFixed(2)}${suffix}`
          : `${prefix}${target.toLocaleString()}${suffix}`;
      }
    }

    requestAnimationFrame(step);
  }

  // 4. Authentic VoiceClaw Live Discord Simulator
  const simHubBtn = document.getElementById('simHubBtn');
  const simDynamicList = document.getElementById('simDynamicList');
  const simRoomBanner = document.getElementById('simRoomBanner');
  const simRoomTitle = document.getElementById('simRoomTitle');
  const simBitrateLabel = document.getElementById('simBitrateLabel');
  const simStatusText = document.getElementById('simStatusText');
  const simInterfaceTab = document.getElementById('simInterfaceTab');

  let activeRoom = null;
  let isLocked = false;
  let isMuted = false;
  let isChatOpen = false;
  const bitrates = [96, 128, 256, 384, 64];
  let bitrateIdx = 0;
  const names = ["Alex's Room", "Squad Alpha", "Duo Grind", "Late Night Vibes", "Pro Scrims"];
  let nameIdx = 0;
  const regions = ["US East", "EU Central", "Singapore", "US West", "Tokyo"];
  let regionIdx = 0;

  function setStatus(msg) {
    if (simStatusText) {
      simStatusText.textContent = msg;
    }
  }

  function updateRoomPill() {
    if (!activeRoom) return;
    const curName = names[nameIdx];
    let tag = '';
    if (isLocked) {
      tag = `<span style="font-size:0.62rem; font-family:var(--font-mono); color:#ef4444; background:rgba(239,68,68,0.15); padding:1px 5px; border-radius:3px; margin-left:auto;">LOCKED</span>`;
    } else {
      tag = `<span style="font-size:0.62rem; font-family:var(--font-mono); color:#22c55e; background:rgba(34,197,94,0.15); padding:1px 5px; border-radius:3px; margin-left:auto;">LIVE</span>`;
    }

    activeRoom.innerHTML = `
      <div class="sim-chan-main">
        <svg class="sim-chan-ico" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>
        </svg>
        <span class="sim-chan-label">${curName} [1/4]</span>
      </div>
      ${tag}
    `;

    if (simRoomTitle) {
      simRoomTitle.textContent = `${curName} [1/4]`;
    }
  }

  function spawnRoom() {
    if (activeRoom) {
      setStatus(`[Notice] You are already connected to ${names[nameIdx]}. Use the 15 buttons below to control it.`);
      return;
    }

    activeRoom = document.createElement('div');
    activeRoom.className = 'sim-channel-row voice active-room';
    activeRoom.title = 'Your Active Channel';
    activeRoom.addEventListener('click', () => {
      setStatus(`[View] Focused on ${names[nameIdx]} voice room.`);
    });

    simDynamicList.appendChild(activeRoom);
    if (simRoomBanner) simRoomBanner.style.display = 'flex';
    if (simHubBtn) {
      simHubBtn.style.opacity = '0.45';
    }

    updateRoomPill();
    setStatus(`[Event] Channel "${names[nameIdx]}" spawned in 12ms. You have full host permissions.`);
  }

  function deleteRoom() {
    if (!activeRoom) {
      setStatus('[Action] No active room to delete. Click "Join to Create" first.');
      return;
    }

    const oldName = names[nameIdx];
    activeRoom.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
    activeRoom.style.opacity = '0';
    activeRoom.style.transform = 'scale(0.95)';

    setTimeout(() => {
      if (activeRoom) {
        activeRoom.remove();
        activeRoom = null;
      }
      if (simRoomBanner) simRoomBanner.style.display = 'none';
      if (simHubBtn) {
        simHubBtn.style.opacity = '1';
      }
      isLocked = false;
      const btnLock = document.getElementById('btnVcLock');
      if (btnLock) btnLock.classList.remove('active');

      setStatus(`[Cleanup] Channel "${oldName}" empty -> Purged in 9ms. Zero leftover clutter in server.`);
    }, 200);
  }

  if (simHubBtn) {
    simHubBtn.addEventListener('click', () => {
      spawnRoom();
    });
  }

  if (simInterfaceTab) {
    simInterfaceTab.addEventListener('click', () => {
      setStatus('[View] Switched to #interface control console.');
    });
  }

  // Bind All 15 Button Actions
  const btnVcRename = document.getElementById('btnVcRename');
  if (btnVcRename) {
    btnVcRename.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      nameIdx = (nameIdx + 1) % names.length;
      updateRoomPill();
      setStatus(`[Rename] Channel renamed to "${names[nameIdx]}". Updated across all Discord clients in 15ms.`);
    });
  }

  const btnVcBitrate = document.getElementById('btnVcBitrate');
  if (btnVcBitrate) {
    btnVcBitrate.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      bitrateIdx = (bitrateIdx + 1) % bitrates.length;
      const curBitrate = bitrates[bitrateIdx];
      if (simBitrateLabel) {
        simBitrateLabel.textContent = `Channel Owner • ${curBitrate} kbps Studio Audio`;
      }
      setStatus(`[Bitrate] Voice audio quality set to ${curBitrate} kbps. Crystal-clear Opus stream active.`);
    });
  }

  const btnVcLock = document.getElementById('btnVcLock');
  if (btnVcLock) {
    btnVcLock.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      isLocked = !isLocked;
      btnVcLock.classList.toggle('active', isLocked);
      updateRoomPill();
      setStatus(isLocked
        ? `[Permission] Channel locked. Only trusted friends or invited members can join.`
        : `[Permission] Channel unlocked. Public access open.`);
    });
  }

  const btnVcMute = document.getElementById('btnVcMute');
  if (btnVcMute) {
    btnVcMute.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      isMuted = !isMuted;
      btnVcMute.classList.toggle('active', isMuted);
      setStatus(isMuted
        ? `[Audio] Channel muted for non-hosts. Push-to-talk enforce enabled.`
        : `[Audio] Channel unmuted. Open microphone voice active.`);
    });
  }

  const btnVcChat = document.getElementById('btnVcChat');
  if (btnVcChat) {
    btnVcChat.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      isChatOpen = !isChatOpen;
      btnVcChat.classList.toggle('active', isChatOpen);
      setStatus(isChatOpen
        ? `[Chat] Private in-channel text thread opened for connected voice members.`
        : `[Chat] In-channel text thread minimized.`);
    });
  }

  const btnVcTrust = document.getElementById('btnVcTrust');
  if (btnVcTrust) {
    btnVcTrust.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Trust] Added friend to trusted whitelist. They can now join even when locked.`);
    });
  }

  const btnVcUntrust = document.getElementById('btnVcUntrust');
  if (btnVcUntrust) {
    btnVcUntrust.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Untrust] Member removed from trusted bypass list.`);
    });
  }

  const btnVcInvite = document.getElementById('btnVcInvite');
  if (btnVcInvite) {
    btnVcInvite.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Invite] 1-click temporary voice invite link generated: https://discord.gg/vc-temp-8491`);
    });
  }

  const btnVcKick = document.getElementById('btnVcKick');
  if (btnVcKick) {
    btnVcKick.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Kick] Selected member disconnected from voice room back to lobby.`);
    });
  }

  const btnVcRegion = document.getElementById('btnVcRegion');
  if (btnVcRegion) {
    btnVcRegion.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      regionIdx = (regionIdx + 1) % regions.length;
      setStatus(`[RTC Region] Voice server region seamlessly switched to ${regions[regionIdx]} (< 22ms ping).`);
    });
  }

  const btnVcBlock = document.getElementById('btnVcBlock');
  if (btnVcBlock) {
    btnVcBlock.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Block] Member blacklisted and denied voice access.`);
    });
  }

  const btnVcUnblock = document.getElementById('btnVcUnblock');
  if (btnVcUnblock) {
    btnVcUnblock.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Unblock / Privacy] Blocklist cleared. Permissions restored.`);
    });
  }

  const btnVcHost = document.getElementById('btnVcHost');
  if (btnVcHost) {
    btnVcHost.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Ownership] You claimed active host crown of "${names[nameIdx]}".`);
    });
  }

  const btnVcTransfer = document.getElementById('btnVcTransfer');
  if (btnVcTransfer) {
    btnVcTransfer.addEventListener('click', () => {
      if (!activeRoom) spawnRoom();
      setStatus(`[Transfer] Ownership crown transferred to next member in queue.`);
    });
  }

  const btnVcDelete = document.getElementById('btnVcDelete');
  if (btnVcDelete) {
    btnVcDelete.addEventListener('click', () => {
      deleteRoom();
    });
  }

  // 5. FAQ Accordion
  const faqItems = document.querySelectorAll('.faq-item');
  faqItems.forEach(item => {
    const btn = item.querySelector('.faq-btn');
    const content = item.querySelector('.faq-content');

    if (btn && content) {
      btn.addEventListener('click', () => {
        const isOpen = item.classList.contains('active');

        faqItems.forEach(other => {
          other.classList.remove('active');
          const otherC = other.querySelector('.faq-content');
          if (otherC) otherC.style.maxHeight = null;
        });

        if (!isOpen) {
          item.classList.add('active');
          content.style.maxHeight = content.scrollHeight + 'px';
        }
      });
    }
  });

  // 6. Scroll Spy
  const sections = document.querySelectorAll('section[id]');
  const navLinks = document.querySelectorAll('.nav-link[href^="#"]');

  window.addEventListener('scroll', () => {
    let current = '';
    const scroll = window.scrollY + 120;

    sections.forEach(s => {
      if (scroll >= s.offsetTop && scroll < s.offsetTop + s.offsetHeight) {
        current = s.getAttribute('id');
      }
    });

    navLinks.forEach(link => {
      link.classList.remove('active');
      if (link.getAttribute('href') === `#${current}`) {
        link.classList.add('active');
      }
    });
  }, { passive: true });

  // 7. Real Server Counter Badge
  const liveServerTicker = document.getElementById('liveServerTicker');
  if (liveServerTicker) {
    liveServerTicker.textContent = '14';
  }
});
