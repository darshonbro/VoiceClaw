/**
 * VoiceClaw Cursed Energy Release Background Engine
 * High-performance, GPU-accelerated Canvas particle & ethereal cursed aura simulation.
 * Inspired by Jujutsu Kaisen / Anime Cursed Spirit Energy Releases.
 */

(function () {
  'use strict';

  // Check canvas support
  const canvas = document.getElementById('curseReleaseCanvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  let width = 0;
  let height = 0;
  let dpr = Math.min(window.devicePixelRatio || 1, 2);
  let animationFrameId = null;
  let isTabVisible = true;

  // Cursed Energy Color Palette
  const PALETTE = [
    { r: 139, g: 92,  b: 246, name: 'violet' },    // Pure Cursed Violet
    { r: 168, g: 85,  b: 247, name: 'purple' },    // Domain Purple
    { r: 244, g: 63,  b: 94,  name: 'crimson' },   // Blood Curse Crimson
    { r: 6,   g: 182, b: 212, name: 'cyan' },      // Infinity Cyan Spark
    { r: 99,  g: 102, b: 241, name: 'indigo' },    // Abyssal Indigo
    { r: 236, g: 72,  b: 153, name: 'magenta' }    // Sukuna Flare
  ];

  // Mouse Tracking
  const mouse = {
    x: -9999,
    y: -9999,
    active: false,
    radius: 140
  };

  // Resize Handler
  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    ctx.scale(dpr, dpr);
  }

  window.addEventListener('resize', resize, { passive: true });
  resize();

  // Mouse Listeners
  window.addEventListener('mousemove', (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    mouse.active = true;

    // Emit a couple subtle sparks on movement
    if (Math.random() < 0.35) {
      spawnMouseSpark(mouse.x, mouse.y);
    }
  }, { passive: true });

  window.addEventListener('mouseleave', () => {
    mouse.active = false;
    mouse.x = -9999;
    mouse.y = -9999;
  });

  // Click triggers a manual mini Curse Release burst!
  window.addEventListener('click', (e) => {
    // Only trigger if not clicking buttons or interactive inputs
    if (e.target && (e.target.closest('button') || e.target.closest('input') || e.target.closest('a') || e.target.closest('.modal'))) {
      triggerCurseReleaseBurst(e.clientX, e.clientY, 8, 50);
      return;
    }
    triggerCurseReleaseBurst(e.clientX, e.clientY, 18, 120);
  }, { passive: true });

  // Tab Visibility Watcher
  document.addEventListener('visibilitychange', () => {
    isTabVisible = !document.hidden;
    if (isTabVisible && !animationFrameId) {
      lastTime = performance.now();
      loop(lastTime);
    }
  });

  // ==========================================
  // Cursed Energy Particle Entity
  // ==========================================
  class CurseParticle {
    constructor() {
      this.reset(true);
    }

    reset(initial = false) {
      this.x = Math.random() * width;
      // Start near bottom or dispersed initially
      this.y = initial ? Math.random() * height : height + Math.random() * 60;
      
      // Upward drift with chaotic cursed sway
      this.baseVy = -(0.5 + Math.random() * 1.4);
      this.vy = this.baseVy;
      this.vx = (Math.random() - 0.5) * 0.8;
      
      this.swayFreq = 0.008 + Math.random() * 0.015;
      this.swayAmp = 0.8 + Math.random() * 1.5;
      this.phase = Math.random() * Math.PI * 2;
      
      // Radius & Life
      this.baseRadius = 1.8 + Math.random() * 3.5;
      this.radius = this.baseRadius;
      this.maxLife = 180 + Math.random() * 260;
      this.life = initial ? Math.random() * this.maxLife : 0;
      
      // Color
      this.color = PALETTE[Math.floor(Math.random() * PALETTE.length)];
      this.glowFactor = 0.6 + Math.random() * 0.4;
      this.isSpark = Math.random() < 0.25; // 25% are high-voltage crackles
    }

    update(time) {
      this.life += 1;
      if (this.life >= this.maxLife || this.y < -40 || this.x < -40 || this.x > width + 40) {
        this.reset();
        return;
      }

      // Progress ratio (0 -> 1)
      const progress = this.life / this.maxLife;

      // Sinusoidal organic sway (like rising cursed mist smoke)
      const sway = Math.sin(time * this.swayFreq + this.phase) * this.swayAmp;
      this.x += this.vx + sway * 0.4;
      this.y += this.vy;

      // Size pulse & expansion
      if (progress < 0.2) {
        this.radius = this.baseRadius * (progress / 0.2);
      } else if (progress > 0.7) {
        this.radius = this.baseRadius * (1 - (progress - 0.7) / 0.3);
      } else {
        this.radius = this.baseRadius;
      }

      // Mouse Cursed Attraction / Distortion
      if (mouse.active) {
        const dx = mouse.x - this.x;
        const dy = mouse.y - this.y;
        const dist = Math.hypot(dx, dy);

        if (dist < mouse.radius && dist > 1) {
          const force = (1 - dist / mouse.radius) * 1.5;
          // Swirl around cursor
          this.x += (dx / dist) * force + (-dy / dist) * force * 1.2;
          this.y += (dy / dist) * force + (dx / dist) * force * 1.2;
        }
      }
    }

    draw() {
      const progress = this.life / this.maxLife;
      // Alpha curve: fade in, stay visible, fade out
      let alpha = 0;
      if (progress < 0.2) {
        alpha = progress / 0.2;
      } else if (progress > 0.65) {
        alpha = 1 - (progress - 0.65) / 0.35;
      } else {
        alpha = 1;
      }
      alpha *= 0.55 * this.glowFactor;

      if (alpha <= 0.01) return;

      const { r, g, b } = this.color;

      ctx.save();
      ctx.globalCompositeOperation = 'screen';

      if (this.isSpark) {
        // Crackling lightning ember
        ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.9})`;
        ctx.shadowColor = `rgba(${r}, ${g}, ${b}, ${alpha * 0.8})`;
        ctx.shadowBlur = this.radius * 4;

        ctx.beginPath();
        ctx.arc(this.x, this.y, Math.max(0.8, this.radius * 0.6), 0, Math.PI * 2);
        ctx.fill();

        // Cross flare
        ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${alpha * 0.6})`;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.moveTo(this.x - this.radius * 1.8, this.y);
        ctx.lineTo(this.x + this.radius * 1.8, this.y);
        ctx.moveTo(this.x, this.y - this.radius * 1.8);
        ctx.lineTo(this.x, this.y + this.radius * 1.8);
        ctx.stroke();
      } else {
        // Ethereal smoke orb
        const grad = ctx.createRadialGradient(
          this.x, this.y, 0,
          this.x, this.y, this.radius * 2.8
        );
        grad.addColorStop(0, `rgba(255, 255, 255, ${alpha * 0.8})`);
        grad.addColorStop(0.35, `rgba(${r}, ${g}, ${b}, ${alpha * 0.7})`);
        grad.addColorStop(0.7, `rgba(${r}, ${g}, ${b}, ${alpha * 0.2})`);
        grad.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius * 2.8, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.restore();
    }
  }

  // ==========================================
  // Curse Release Shockwave Ring
  // ==========================================
  class CurseShockwave {
    constructor(x, y, maxR = 400, color = null) {
      this.x = x;
      this.y = y;
      this.radius = 5;
      this.maxRadius = maxR;
      this.growth = 3.5 + Math.random() * 2.5;
      this.color = color || PALETTE[Math.floor(Math.random() * PALETTE.length)];
      this.life = 0;
      this.maxLife = (this.maxRadius - 5) / this.growth;
    }

    update() {
      this.life += 1;
      this.radius += this.growth;
      return this.life < this.maxLife;
    }

    draw() {
      const progress = this.life / this.maxLife;
      const alpha = Math.sin(progress * Math.PI) * 0.35;
      if (alpha <= 0.01) return;

      const { r, g, b } = this.color;

      ctx.save();
      ctx.globalCompositeOperation = 'screen';
      ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
      ctx.lineWidth = Math.max(1, (1 - progress) * 4);
      ctx.shadowColor = `rgba(${r}, ${g}, ${b}, ${alpha * 0.8})`;
      ctx.shadowBlur = 18;

      ctx.beginPath();
      ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
      ctx.stroke();

      // Subtle inner secondary ring
      if (this.radius > 40) {
        ctx.strokeStyle = `rgba(255, 255, 255, ${alpha * 0.4})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.radius * 0.92, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.restore();
    }
  }

  // ==========================================
  // Floating Cursed Ribbon Waves (Domain Energy)
  // ==========================================
  class CurseRibbon {
    constructor(index, total) {
      this.index = index;
      this.total = total;
      this.yRatio = (index + 1) / (total + 1);
      this.speed = 0.0006 + index * 0.0003;
      this.color = PALETTE[index % PALETTE.length];
      this.heightAmp = 60 + index * 25;
    }

    draw(time) {
      const baseY = height * this.yRatio;
      const { r, g, b } = this.color;

      ctx.save();
      ctx.globalCompositeOperation = 'screen';

      ctx.beginPath();
      ctx.moveTo(0, baseY);

      const segments = 12;
      for (let i = 0; i <= segments; i++) {
        const x = (width / segments) * i;
        const wave1 = Math.sin(time * this.speed + i * 0.4 + this.index) * this.heightAmp;
        const wave2 = Math.cos(time * (this.speed * 1.5) + i * 0.25) * (this.heightAmp * 0.4);
        const y = baseY + wave1 + wave2;

        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }

      // Complete path to bottom for filled dark glow
      ctx.lineTo(width, height);
      ctx.lineTo(0, height);
      ctx.closePath();

      const grad = ctx.createLinearGradient(0, baseY - this.heightAmp, 0, baseY + this.heightAmp * 2);
      grad.addColorStop(0, `rgba(${r}, ${g}, ${b}, 0.06)`);
      grad.addColorStop(0.5, `rgba(${r}, ${g}, ${b}, 0.03)`);
      grad.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`);

      ctx.fillStyle = grad;
      ctx.fill();

      ctx.restore();
    }
  }

  // Particle Pools
  const PARTICLE_COUNT = 75;
  const particles = Array.from({ length: PARTICLE_COUNT }, () => new CurseParticle());
  const shockwaves = [];
  const mouseSparks = [];
  const ribbons = [
    new CurseRibbon(0, 3),
    new CurseRibbon(1, 3),
    new CurseRibbon(2, 3)
  ];

  // Helper: Trigger Curse Release Burst
  function triggerCurseReleaseBurst(x, y, particleCount = 12, maxRadius = 350) {
    shockwaves.push(new CurseShockwave(x, y, maxRadius));

    for (let i = 0; i < particleCount; i++) {
      const angle = (Math.PI * 2 / particleCount) * i + (Math.random() - 0.5) * 0.5;
      const speed = 1.5 + Math.random() * 3.5;
      mouseSparks.push({
        x: x,
        y: y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 1.2,
        radius: 1.5 + Math.random() * 3,
        color: PALETTE[Math.floor(Math.random() * PALETTE.length)],
        life: 0,
        maxLife: 40 + Math.random() * 50
      });
    }

    // Keep arrays bounded
    if (shockwaves.length > 8) shockwaves.shift();
    if (mouseSparks.length > 80) mouseSparks.splice(0, 20);
  }

  function spawnMouseSpark(x, y) {
    mouseSparks.push({
      x: x + (Math.random() - 0.5) * 14,
      y: y + (Math.random() - 0.5) * 14,
      vx: (Math.random() - 0.5) * 1.5,
      vy: -0.5 - Math.random() * 2,
      radius: 1.2 + Math.random() * 2,
      color: PALETTE[Math.floor(Math.random() * PALETTE.length)],
      life: 0,
      maxLife: 30 + Math.random() * 35
    });
    if (mouseSparks.length > 80) mouseSparks.shift();
  }

  // Automatic Periodic Ambient "Curse Release" Bursts
  let lastAmbientBurst = performance.now();
  const BURST_INTERVAL = 7000; // Every 7 seconds

  // Main Render Loop
  let lastTime = performance.now();

  function loop(currentTime) {
    if (!isTabVisible) {
      animationFrameId = null;
      return;
    }

    // Periodic ambient curse release from bottom center
    if (currentTime - lastAmbientBurst > BURST_INTERVAL) {
      const burstX = width * (0.3 + Math.random() * 0.4);
      const burstY = height * (0.65 + Math.random() * 0.3);
      triggerCurseReleaseBurst(burstX, burstY, 15, Math.min(width, height) * 0.7);
      lastAmbientBurst = currentTime;
    }

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // 1. Draw Cursed Energy Ribbons
    ribbons.forEach((r) => r.draw(currentTime));

    // 2. Draw & Update Shockwaves
    for (let i = shockwaves.length - 1; i >= 0; i--) {
      const alive = shockwaves[i].update();
      if (alive) {
        shockwaves[i].draw();
      } else {
        shockwaves.splice(i, 1);
      }
    }

    // 3. Draw & Update Floating Particles
    for (let i = 0; i < particles.length; i++) {
      particles[i].update(currentTime);
      particles[i].draw();
    }

    // 4. Draw & Update Mouse / Burst Sparks
    for (let i = mouseSparks.length - 1; i >= 0; i--) {
      const s = mouseSparks[i];
      s.life += 1;
      s.x += s.vx;
      s.y += s.vy;
      s.vy += 0.04; // slight gravity for burst sparks
      s.vx *= 0.98;

      const progress = s.life / s.maxLife;
      if (progress >= 1) {
        mouseSparks.splice(i, 1);
        continue;
      }

      const alpha = (1 - progress) * 0.75;
      const { r, g, b } = s.color;

      ctx.save();
      ctx.globalCompositeOperation = 'screen';
      ctx.fillStyle = `rgba(255, 255, 255, ${alpha})`;
      ctx.shadowColor = `rgba(${r}, ${g}, ${b}, ${alpha * 0.9})`;
      ctx.shadowBlur = s.radius * 3;

      ctx.beginPath();
      ctx.arc(s.x, s.y, s.radius * (1 - progress * 0.4), 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    animationFrameId = requestAnimationFrame(loop);
  }

  // Trigger an initial majestic curse release right after load
  setTimeout(() => {
    triggerCurseReleaseBurst(width * 0.5, height * 0.65, 25, Math.min(width, height) * 0.85);
  }, 400);

  animationFrameId = requestAnimationFrame(loop);
})();
