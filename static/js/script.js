window.addEventListener("load", () => {
  const hash = window.location.hash;
  if (!hash) return;
  const target = document.querySelector(hash);
  if (target) target.scrollIntoView({ behavior: "smooth" });
});

document.addEventListener("DOMContentLoaded", () => {
    const slides = document.querySelectorAll(".hero-carousel .slide");
    if (!slides.length) return;

    let current = 0;
    setInterval(() => {
        slides[current].classList.remove("active");
        current = (current + 1) % slides.length;
        slides[current].classList.add("active");
    }, 3000);
});

document.addEventListener("DOMContentLoaded", () => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const canvas = document.createElement("canvas");
  canvas.className = "polka-weather-canvas";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);

  const context = canvas.getContext("2d", { alpha: true });
  if (!context) {
    canvas.remove();
    return;
  }

  const colors = [
    [63, 112, 104],
    [125, 50, 175],
    [242, 139, 74],
    [62, 133, 192],
    [226, 92, 132]
  ];
  const clouds = [];
  const particles = [];
  let width = 0;
  let height = 0;
  let lastFrame = 0;
  const month = new Date().getMonth();
  const weatherMode = month === 11 || month < 2 ? "snow" : month < 5 ? "rain" : month < 8 ? "mist" : "leaves";

  function resetParticle(particle, initial) {
    particle.x = Math.random() * width;
    particle.direction = Math.random() < .28 ? -1 : 1;
    particle.y = initial
      ? Math.random() * height
      : particle.direction > 0 ? -24 : height + 24;
    particle.speed = 1.1 + Math.random() * 2.1;
    particle.size = .8 + Math.random() * 2.2;
    particle.drift = (Math.random() - .5) * .5;
    particle.alpha = .2 + Math.random() * .2;
    particle.length = 22 + Math.random() * 54;
    particle.angle = (Math.random() - .5) * .48;
    particle.spin = (Math.random() - .5) * .012;
    particle.bob = Math.random() * Math.PI * 2;
  }

  function resize() {
    const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    if (!clouds.length) {
      colors.forEach((color, index) => {
        clouds.push({
          x: Math.random() * width,
          y: Math.random() * height,
          radius: 110 + Math.random() * 160,
          phase: index * 1.17,
          color
        });
      });
      for (let index = 0; index < 48; index += 1) {
        const particle = {};
        resetParticle(particle, true);
        particles.push(particle);
      }
    }
  }

  function drawSky(time) {
    const hour = new Date().getHours();
    const daylight = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
    const sky = context.createLinearGradient(0, 0, 0, height);
    sky.addColorStop(0, `rgba(32, 66, 96, ${.13 * (1 - daylight)})`);
    sky.addColorStop(1, `rgba(255, 190, 112, ${.09 * daylight})`);
    context.fillStyle = sky;
    context.fillRect(0, 0, width, height);

    clouds.forEach((cloud) => {
      const x = cloud.x + Math.sin(time * .00008 + cloud.phase) * 80;
      const y = cloud.y + Math.cos(time * .00006 + cloud.phase) * 46;
      const radius = cloud.radius * (1 + Math.sin(time * .00018 + cloud.phase) * .09);
      const glow = context.createRadialGradient(x, y, 0, x, y, radius);
      glow.addColorStop(0, `rgba(${cloud.color.join(",")}, .22)`);
      glow.addColorStop(1, `rgba(${cloud.color.join(",")}, 0)`);
      context.fillStyle = glow;
      context.beginPath();
      context.arc(x, y, radius, 0, Math.PI * 2);
      context.fill();
    });
  }

  function drawWeather() {
    for (let first = 0; first < particles.length; first += 1) {
      for (let second = first + 1; second < particles.length; second += 1) {
        const dx = particles[first].x - particles[second].x;
        const dy = particles[first].y - particles[second].y;
        if ((dx * dx) + (dy * dy) < 150) {
          const drift = particles[first].drift;
          particles[first].drift = particles[second].drift;
          particles[second].drift = drift;
          particles[first].angle += .035;
          particles[second].angle -= .035;
        }
      }
    }

    particles.forEach((particle, index) => {
      particle.y += particle.speed * particle.direction;
      particle.x += particle.drift + Math.sin(particle.y * .015 + particle.bob) * .18;
      particle.angle += particle.spin;

      if (weatherMode === "rain") {
        context.strokeStyle = `rgba(55, 112, 158, ${particle.alpha})`;
        context.beginPath();
        context.moveTo(particle.x, particle.y);
        context.lineTo(particle.x - 2, particle.y + 10 + particle.size * 3);
        context.stroke();
      } else if (weatherMode === "snow") {
        context.fillStyle = `rgba(255,255,255,${particle.alpha + .16})`;
        context.beginPath();
        context.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        context.fill();
      } else if (weatherMode === "mist") {
        context.strokeStyle = `rgba(53, 132, 148, ${particle.alpha * .82})`;
        context.lineWidth = 1.5;
        context.save();
        context.translate(particle.x, particle.y);
        context.rotate(particle.angle);
        context.beginPath();
        context.moveTo(-particle.length / 2, 0);
        context.lineTo(particle.length / 2, 0);
        context.stroke();
        context.restore();
        if (index % 9 === 0) {
          context.strokeStyle = `rgba(55, 112, 158, ${particle.alpha * .75})`;
          context.beginPath();
          context.moveTo(particle.x + 12, particle.y - 4);
          context.lineTo(particle.x + 9, particle.y + 8);
          context.stroke();
        }
      } else {
        context.fillStyle = `rgba(177, 112, 42, ${particle.alpha})`;
        context.save();
        context.translate(particle.x, particle.y);
        context.rotate(particle.y * .012);
        context.fillRect(-particle.size, -particle.size / 2, particle.size * 2.4, particle.size);
        context.restore();
      }

      if (
        particle.y > height + 30 ||
        particle.y < -30 ||
        particle.x < -60 ||
        particle.x > width + 60
      ) {
        resetParticle(particle, false);
      }
    });
  }

  function animate(time) {
    if (time - lastFrame < 32) {
      requestAnimationFrame(animate);
      return;
    }
    lastFrame = time;
    context.clearRect(0, 0, width, height);
    drawSky(time);
    drawWeather();
    requestAnimationFrame(animate);
  }

  resize();
  window.addEventListener("resize", resize, { passive: true });
  requestAnimationFrame(animate);
});
