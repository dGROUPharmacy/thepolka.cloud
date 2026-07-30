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
  const canvas = document.getElementById("polka-motion");
  if (!canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const context = canvas.getContext("2d", { alpha: true });
  if (!context) return;

  const palette = [
    [63, 112, 104],
    [125, 50, 175],
    [242, 139, 74],
    [62, 133, 192],
    [226, 92, 132]
  ];
  const dots = [];
  const pulses = [];
  const weather = [];
  const lineArt = [];
  let width = 0;
  let height = 0;
  let ratio = 1;
  let lastFrame = 0;
  const month = new Date().getMonth();
  const season = month === 11 || month < 2 ? "snow" : month < 5 ? "rain" : month < 8 ? "mist" : "rain";
  const weatherMode = Math.random() < .72 ? season : "clear";

  function resize() {
    ratio = Math.min(window.devicePixelRatio || 1, 1.5);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    if (!dots.length) {
      for (let index = 0; index < 7; index += 1) {
        const color = palette[index % palette.length];
        dots.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - .5) * .16,
          vy: (Math.random() - .5) * .16,
          radius: 90 + Math.random() * 150,
          phase: Math.random() * Math.PI * 2,
          color
        });
      }
      for (let index = 0; index < 54; index += 1) {
        weather.push({
          x: Math.random() * width,
          y: Math.random() * height,
          speed: 1 + Math.random() * 2.2,
          length: 6 + Math.random() * 13,
          drift: (Math.random() - .5) * .55,
          alpha: .08 + Math.random() * .18,
          size: 1 + Math.random() * 2.4
        });
      }
      for (let index = 0; index < 5; index += 1) {
        lineArt.push({
          x: Math.random() * width,
          y: Math.random() * height,
          scale: 35 + Math.random() * 85,
          phase: Math.random() * Math.PI * 2,
          speed: .00008 + Math.random() * .00008
        });
      }
    }
  }

  function choreograph(element) {
    const box = element.getBoundingClientRect();
    const originX = box.left + box.width / 2;
    const originY = box.top + box.height / 2;
    palette.forEach((color, index) => {
      pulses.push({
        x: originX,
        y: originY,
        radius: 8 + index * 7,
        alpha: .34 - index * .035,
        delay: index * 45,
        born: performance.now(),
        color
      });
    });
  }

  document.querySelectorAll(".nav-link").forEach((link) => {
    link.addEventListener("pointerenter", () => choreograph(link), { passive: true });
    link.addEventListener("focus", () => choreograph(link));
  });

  function paintBlob(dot, time) {
    dot.x += dot.vx + Math.sin(time * .00016 + dot.phase) * .045;
    dot.y += dot.vy + Math.cos(time * .00013 + dot.phase) * .045;
    const margin = dot.radius * .35;
    if (dot.x < -margin) dot.x = width + margin;
    if (dot.x > width + margin) dot.x = -margin;
    if (dot.y < -margin) dot.y = height + margin;
    if (dot.y > height + margin) dot.y = -margin;
    const breath = dot.radius * (1 + Math.sin(time * .00028 + dot.phase) * .12);
    const gradient = context.createRadialGradient(dot.x, dot.y, 0, dot.x, dot.y, breath);
    gradient.addColorStop(0, `rgba(${dot.color.join(",")}, .12)`);
    gradient.addColorStop(.55, `rgba(${dot.color.join(",")}, .055)`);
    gradient.addColorStop(1, `rgba(${dot.color.join(",")}, 0)`);
    context.fillStyle = gradient;
    context.beginPath();
    context.arc(dot.x, dot.y, breath, 0, Math.PI * 2);
    context.fill();
  }

  function paintSky(time) {
    const hour = new Date().getHours();
    const daylight = Math.max(0, Math.sin(((hour - 6) / 12) * Math.PI));
    const shade = context.createLinearGradient(0, 0, 0, height);
    shade.addColorStop(0, `rgba(18, 35, 62, ${.13 * (1 - daylight)})`);
    shade.addColorStop(1, `rgba(255, 194, 126, ${.045 * daylight})`);
    context.fillStyle = shade;
    context.fillRect(0, 0, width, height);

    lineArt.forEach((line, index) => {
      const driftX = line.x + Math.sin(time * line.speed + line.phase) * 38;
      const driftY = line.y + Math.cos(time * line.speed * .7 + line.phase) * 24;
      context.strokeStyle = `rgba(63, 112, 104, ${.065 + index * .008})`;
      context.lineWidth = 1;
      context.beginPath();
      for (let step = 0; step <= 42; step += 1) {
        const angle = step * .31 + time * .00008;
        const radius = line.scale * (step / 42);
        const x = driftX + Math.cos(angle + line.phase) * radius;
        const y = driftY + Math.sin(angle * 1.7) * radius * .42;
        if (!step) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.stroke();
    });
  }

  function paintWeather() {
    if (weatherMode === "clear") return;
    weather.forEach((drop) => {
      if (weatherMode === "snow") {
        drop.y += drop.speed * .35;
        drop.x += Math.sin(drop.y * .018) * .32 + drop.drift;
        context.fillStyle = `rgba(255,255,255,${drop.alpha + .12})`;
        context.beginPath();
        context.arc(drop.x, drop.y, drop.size, 0, Math.PI * 2);
        context.fill();
      } else if (weatherMode === "mist") {
        drop.x += drop.speed * .32;
        drop.y += Math.sin(drop.x * .012) * .08;
        context.strokeStyle = `rgba(98,174,187,${drop.alpha * .55})`;
        context.beginPath();
        context.moveTo(drop.x, drop.y);
        context.lineTo(drop.x + drop.length * 2.8, drop.y);
        context.stroke();
      } else {
        drop.y += drop.speed;
        drop.x += drop.drift;
        context.strokeStyle = `rgba(74,126,166,${drop.alpha})`;
        context.lineWidth = .8;
        context.beginPath();
        context.moveTo(drop.x, drop.y);
        context.lineTo(drop.x - 2, drop.y + drop.length);
        context.stroke();
      }
      if (drop.y > height + 20 || drop.x > width + 40 || drop.x < -40) {
        drop.x = Math.random() * width;
        drop.y = -20;
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
    paintSky(time);
    dots.forEach((dot) => paintBlob(dot, time));
    paintWeather();
    for (let index = pulses.length - 1; index >= 0; index -= 1) {
      const pulse = pulses[index];
      const age = time - pulse.born - pulse.delay;
      if (age < 0) continue;
      const progress = age / 900;
      if (progress >= 1) {
        pulses.splice(index, 1);
        continue;
      }
      context.strokeStyle = `rgba(${pulse.color.join(",")}, ${pulse.alpha * (1 - progress)})`;
      context.lineWidth = 1.5;
      context.beginPath();
      context.arc(pulse.x, pulse.y, pulse.radius + progress * 92, 0, Math.PI * 2);
      context.stroke();
    }
    requestAnimationFrame(animate);
  }

  resize();
  window.addEventListener("resize", resize, { passive: true });
  requestAnimationFrame(animate);
});
