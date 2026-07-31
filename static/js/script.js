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
  const spaceRim = document.createElement("div");
  spaceRim.className = "polka-space-rim";
  spaceRim.setAttribute("aria-hidden", "true");
  document.body.prepend(spaceRim);

  function addWheels(part) {
    ["a", "b"].forEach((position) => {
      const wheel = document.createElement("i");
      wheel.className = `polka-train-wheel polka-train-wheel-${position}`;
      part.appendChild(wheel);
    });
  }

  function createRail(orientation) {
    const rail = document.createElement("div");
    rail.className = `polka-train-rail polka-train-${orientation}`;
    rail.setAttribute("aria-hidden", "true");
    const consist = document.createElement("div");
    consist.className = "polka-train-consist";
    ["engine", "car", "car", "car", "car", "engine"].forEach((kind, index, parts) => {
      const part = document.createElement("span");
      part.className = `polka-train-${kind}`;
      if (kind === "car" && index === 4) part.classList.add("polka-train-caboose");
      if (kind === "engine") {
        const end = index === 0 ? "start" : "end";
        part.classList.add(`polka-train-engine-${end}`);
        const stack = document.createElement("i");
        stack.className = "polka-train-smokestack";
        part.appendChild(stack);
        const steam = document.createElement("i");
        steam.className = `polka-train-steam polka-train-steam-${end}`;
        part.appendChild(steam);
      }
      addWheels(part);
      consist.appendChild(part);
    });
    rail.appendChild(consist);
    document.body.appendChild(rail);
    return { rail, consist };
  }

  const vertical = createRail("vertical");
  const horizontal = createRail("horizontal");
  const sidebar = document.querySelector(".sidebar");

  function updateTrainGeometry() {
    const boundary = sidebar ? sidebar.getBoundingClientRect().right : 280;
    vertical.rail.style.left = `${Math.round(boundary - vertical.rail.offsetWidth / 2)}px`;
    horizontal.rail.style.left = `${Math.round(boundary)}px`;

    const pageMax = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    const sidebarMax = sidebar ? Math.max(1, sidebar.scrollHeight - sidebar.clientHeight) : 1;
    const pageProgress = window.scrollY / pageMax;
    const sidebarProgress = sidebar ? sidebar.scrollTop / sidebarMax : 0;
    const verticalProgress = Math.min(1, Math.max(0, Math.max(pageProgress, sidebarProgress)));
    const verticalTravel = Math.max(0, window.innerHeight - vertical.consist.offsetHeight - 24);
    vertical.consist.style.transform = `translateY(${Math.round(verticalProgress * verticalTravel)}px)`;

    const horizontalMax = Math.max(1, document.documentElement.scrollWidth - window.innerWidth);
    const horizontalProgress = Math.min(1, Math.max(0, window.scrollX / horizontalMax));
    const horizontalTravel = Math.max(0, window.innerWidth - boundary - horizontal.consist.offsetWidth - 24);
    horizontal.consist.style.transform = `translateX(${Math.round(horizontalProgress * horizontalTravel)}px)`;
  }

  updateTrainGeometry();
  window.addEventListener("scroll", updateTrainGeometry, { passive: true });
  window.addEventListener("resize", updateTrainGeometry, { passive: true });
  if (sidebar) sidebar.addEventListener("scroll", updateTrainGeometry, { passive: true });
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
  const aerialVehicles = [];
  let width = 0;
  let height = 0;
  let lastFrame = 0;
  const month = new Date().getMonth();
  const weatherMode = month === 11 || month < 2 ? "snow" : month < 5 ? "rain" : month < 8 ? "mist" : "leaves";

  function resetParticle(particle, initial) {
    particle.flightDirection = Math.random() < .5 ? -1 : 1;
    particle.x = initial
      ? Math.random() * width
      : particle.flightDirection > 0 ? -36 : width + 36;
    particle.direction = Math.random() < .28 ? -1 : 1;
    particle.y = Math.random() * height;
    particle.speed = 1.1 + Math.random() * 2.1;
    particle.horizontalSpeed = .8 + Math.random() * 1.55;
    particle.verticalDrift = (Math.random() - .5) * .42;
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
      for (let index = 0; index < 30; index += 1) {
        const particle = {};
        resetParticle(particle, true);
        particles.push(particle);
      }
      [
        { type: "jet", active: true, speed: .78, scale: 38 },
        { type: "jet", active: false, speed: .66, scale: 32 },
        { type: "rocket", active: false, speed: .48, scale: 31 },
        { type: "balloon", active: false, speed: .34, scale: 35 },
        { type: "flying-car", active: false, speed: .54, scale: 27 },
        { type: "parachute", active: false, speed: .34, scale: 24 },
        { type: "parachute", active: false, speed: .29, scale: 21 }
      ].forEach((vehicle, index) => {
        const initialDirection = Math.random() < .5 ? -1 : 1;
        aerialVehicles.push({
          ...vehicle,
          direction: initialDirection,
          x: initialDirection > 0 ? -90 : width + 90,
          y: height * (.12 + index * .12),
          slope: (Math.random() - .5) * .2,
          nextAppearance: performance.now() + 4000 + Math.random() * 12000
        });
      });
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

  function drawHummingbird(x, y, size, angle, alpha, wingPhase, colorIndex, facing) {
    const flap = Math.sin(wingPhase * 4.6);
    const wingRise = flap * size * .95;
    const wingBend = (0.42 + Math.abs(flap) * .5) * size;
    const color = colors[colorIndex % colors.length];
    context.save();
    context.translate(x, y + Math.cos(wingPhase * 4.6) * size * .12);
    context.rotate(angle * .45);
    context.scale(facing, 1);
    context.strokeStyle = `rgba(34, 65, 61, ${Math.min(1, alpha + .34)})`;
    context.fillStyle = `rgba(${color.join(",")}, ${Math.min(.82, alpha + .22)})`;
    context.lineWidth = Math.max(1.15, size * .16);
    context.lineCap = "round";
    context.lineJoin = "round";

    /* Two broad, jointed wings create the familiar flying-bird silhouette. */
    context.beginPath();
    context.moveTo(0, 0);
    context.quadraticCurveTo(-size * .48, -wingBend, -size * 1.42, wingRise);
    context.moveTo(0, 0);
    context.quadraticCurveTo(size * .48, -wingBend, size * 1.42, wingRise);
    context.stroke();

    /* Feathered lower edges make each wing read as a wing, not a jet streak. */
    context.globalAlpha = .72;
    context.beginPath();
    context.moveTo(-size * 1.34, wingRise);
    context.quadraticCurveTo(-size * .7, -wingBend * .48, 0, size * .12);
    context.quadraticCurveTo(size * .7, -wingBend * .48, size * 1.34, wingRise);
    context.stroke();
    context.globalAlpha = 1;

    context.beginPath();
    context.ellipse(0, size * .1, size * .23, size * .5, 0, 0, Math.PI * 2);
    context.fill();

    context.beginPath();
    context.moveTo(0, -size * .35);
    context.lineTo(size * .18, -size * .62);
    context.lineTo(0, -size * .52);
    context.closePath();
    context.fill();

    context.beginPath();
    context.moveTo(-size * .18, size * .48);
    context.lineTo(-size * .42, size * .78);
    context.moveTo(size * .18, size * .48);
    context.lineTo(size * .42, size * .78);
    context.stroke();
    context.restore();
  }

  function drawJet(vehicle) {
    context.save();
    context.translate(vehicle.x, vehicle.y);
    context.rotate(vehicle.slope * .38);
    context.scale(vehicle.direction, 1);
    context.fillStyle = "rgba(58, 78, 92, .58)";
    context.strokeStyle = "rgba(255, 255, 255, .3)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(vehicle.scale * .92, 0);
    context.lineTo(vehicle.scale * .18, -vehicle.scale * .12);
    context.lineTo(-vehicle.scale * .68, -vehicle.scale * .09);
    context.lineTo(-vehicle.scale * .92, 0);
    context.lineTo(-vehicle.scale * .68, vehicle.scale * .09);
    context.lineTo(vehicle.scale * .18, vehicle.scale * .12);
    context.closePath();
    context.fill();
    context.stroke();
    context.beginPath();
    context.moveTo(-vehicle.scale * .12, 0);
    context.lineTo(-vehicle.scale * .55, -vehicle.scale * .48);
    context.lineTo(vehicle.scale * .18, -vehicle.scale * .08);
    context.lineTo(-vehicle.scale * .55, vehicle.scale * .48);
    context.closePath();
    context.fill();
    context.restore();
  }

  function drawRocket(vehicle) {
    context.save();
    context.translate(vehicle.x, vehicle.y);
    context.rotate(-1.08 * vehicle.direction);
    context.fillStyle = "rgba(86, 91, 112, .58)";
    context.beginPath();
    context.moveTo(vehicle.scale * .72, 0);
    context.quadraticCurveTo(vehicle.scale * .48, -vehicle.scale * .2, 0, -vehicle.scale * .16);
    context.lineTo(-vehicle.scale * .58, -vehicle.scale * .12);
    context.lineTo(-vehicle.scale * .58, vehicle.scale * .12);
    context.lineTo(0, vehicle.scale * .16);
    context.quadraticCurveTo(vehicle.scale * .48, vehicle.scale * .2, vehicle.scale * .72, 0);
    context.fill();
    context.fillStyle = "rgba(238, 139, 70, .48)";
    context.beginPath();
    context.moveTo(-vehicle.scale * .58, -vehicle.scale * .08);
    context.lineTo(-vehicle.scale * 1.05, 0);
    context.lineTo(-vehicle.scale * .58, vehicle.scale * .08);
    context.closePath();
    context.fill();
    context.restore();
  }

  function drawBalloon(vehicle) {
    context.save();
    context.translate(vehicle.x, vehicle.y);
    const sway = Math.sin(vehicle.y * .018) * .08;
    context.rotate(sway);
    const gradient = context.createLinearGradient(
      -vehicle.scale * .5,
      0,
      vehicle.scale * .5,
      0
    );
    gradient.addColorStop(0, "rgba(226, 92, 132, .58)");
    gradient.addColorStop(.5, "rgba(242, 139, 74, .62)");
    gradient.addColorStop(1, "rgba(125, 50, 175, .54)");
    context.fillStyle = gradient;
    context.beginPath();
    context.ellipse(0, 0, vehicle.scale * .52, vehicle.scale * .68, 0, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = "rgba(70, 66, 62, .48)";
    context.lineWidth = 1;
    context.beginPath();
    context.moveTo(-vehicle.scale * .22, vehicle.scale * .55);
    context.lineTo(-vehicle.scale * .12, vehicle.scale * .92);
    context.moveTo(vehicle.scale * .22, vehicle.scale * .55);
    context.lineTo(vehicle.scale * .12, vehicle.scale * .92);
    context.stroke();
    context.fillStyle = "rgba(112, 78, 48, .62)";
    context.fillRect(
      -vehicle.scale * .18,
      vehicle.scale * .88,
      vehicle.scale * .36,
      vehicle.scale * .24
    );
    context.restore();
  }

  function drawFlyingCar(vehicle, time) {
    context.save();
    context.translate(vehicle.x, vehicle.y + Math.sin(time * .0013) * 4);
    context.rotate(vehicle.slope * .18);
    context.scale(vehicle.direction, 1);
    const s = vehicle.scale;
    context.fillStyle = "rgba(69, 121, 158, .74)";
    context.strokeStyle = "rgba(31, 47, 59, .68)";
    context.lineWidth = 1.2;
    context.beginPath();
    context.roundRect(-s, -s * .18, s * 2, s * .55, s * .14);
    context.fill();
    context.stroke();
    context.fillStyle = "rgba(167, 217, 231, .7)";
    context.beginPath();
    context.moveTo(-s * .45, -s * .18);
    context.lineTo(-s * .22, -s * .58);
    context.lineTo(s * .48, -s * .58);
    context.lineTo(s * .72, -s * .18);
    context.closePath();
    context.fill();
    context.stroke();
    context.fillStyle = "rgba(30, 38, 43, .85)";
    [-.62, .62].forEach((offset) => {
      context.beginPath();
      context.arc(s * offset, s * .38, s * .2, 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "rgba(202, 228, 235, .75)";
      context.beginPath();
      context.arc(s * offset, s * .38, s * .08, 0, Math.PI * 2);
      context.stroke();
    });
    context.fillStyle = "rgba(255, 226, 132, .75)";
    context.fillRect(s * .9, -s * .02, s * .12, s * .13);
    context.restore();
  }

  function drawParachute(vehicle, time) {
    context.save();
    context.translate(vehicle.x, vehicle.y);
    const sway = Math.sin(time * .0014 + vehicle.scale) * vehicle.scale * .08;
    context.translate(sway, 0);
    context.strokeStyle = "rgba(48, 59, 64, .68)";
    context.fillStyle = "rgba(242, 139, 74, .64)";
    context.lineWidth = 1.2;
    context.beginPath();
    context.arc(0, 0, vehicle.scale * .72, Math.PI, Math.PI * 2);
    context.quadraticCurveTo(0, vehicle.scale * .34, -vehicle.scale * .72, 0);
    context.closePath();
    context.fill();
    context.stroke();
    context.beginPath();
    context.moveTo(-vehicle.scale * .68, 0);
    context.lineTo(-vehicle.scale * .12, vehicle.scale * .92);
    context.moveTo(vehicle.scale * .68, 0);
    context.lineTo(vehicle.scale * .12, vehicle.scale * .92);
    context.stroke();
    context.fillStyle = "rgba(45, 57, 65, .78)";
    context.beginPath();
    context.arc(0, vehicle.scale * 1.02, vehicle.scale * .13, 0, Math.PI * 2);
    context.fill();
    context.beginPath();
    context.moveTo(0, vehicle.scale * 1.15);
    context.lineTo(0, vehicle.scale * 1.58);
    context.moveTo(0, vehicle.scale * 1.3);
    context.lineTo(-vehicle.scale * .28, vehicle.scale * 1.48);
    context.moveTo(0, vehicle.scale * 1.3);
    context.lineTo(vehicle.scale * .28, vehicle.scale * 1.48);
    context.moveTo(0, vehicle.scale * 1.58);
    context.lineTo(-vehicle.scale * .22, vehicle.scale * 1.9);
    context.moveTo(0, vehicle.scale * 1.58);
    context.lineTo(vehicle.scale * .22, vehicle.scale * 1.9);
    context.stroke();
    context.restore();
  }

  function drawAerialVehicles(time) {
    aerialVehicles.forEach((vehicle) => {
      if (!vehicle.active) {
        const activeCount = aerialVehicles.filter((item) => item.active).length;
        const parachutesActive = aerialVehicles.filter((item) => item.active && item.type === "parachute").length;
        const mayAppear = vehicle.type !== "parachute" || parachutesActive < 2;
        if (time >= vehicle.nextAppearance && activeCount < 3 && mayAppear) {
          vehicle.active = true;
          vehicle.direction = Math.random() < .5 ? -1 : 1;
          vehicle.slope = (Math.random() - .5) * .26;
          if (vehicle.type === "balloon") {
            vehicle.x = width * (.14 + Math.random() * .72);
            vehicle.y = height + 90;
          } else if (vehicle.type === "parachute") {
            vehicle.x = width * (.16 + Math.random() * .68);
            vehicle.y = height * (.08 + Math.random() * .18);
          } else {
            vehicle.x = vehicle.direction > 0 ? -100 : width + 100;
            vehicle.y = height * (.07 + Math.random() * .29);
          }
        }
        return;
      }

      if (vehicle.type === "balloon") {
        vehicle.x += Math.sin(time * .00034) * .16;
        vehicle.y -= vehicle.speed;
        drawBalloon(vehicle);
      } else if (vehicle.type === "parachute") {
        vehicle.x += Math.sin(time * .0012 + vehicle.scale) * .18;
        vehicle.y += vehicle.speed;
        drawParachute(vehicle, time);
      } else {
        vehicle.x += vehicle.speed * vehicle.direction;
      }

      if (vehicle.type === "rocket") {
        vehicle.y -= vehicle.speed * .72;
        drawRocket(vehicle);
      } else if (vehicle.type === "jet") {
        vehicle.y += vehicle.slope + Math.sin(time * .00045) * .06;
        drawJet(vehicle);
      } else if (vehicle.type === "flying-car") {
        vehicle.y += vehicle.slope * .3 + Math.sin(time * .0007) * .08;
        drawFlyingCar(vehicle, time);
      }

      const finished = vehicle.x < -130 || vehicle.x > width + 130 || vehicle.y < -110 || vehicle.y > height + 110;
      if (finished) {
        vehicle.active = false;
        const rareDelay = vehicle.type === "flying-car" ? 32000 : vehicle.type === "parachute" ? 16000 : 9000;
        const randomDelay = vehicle.type === "flying-car" ? 36000 : vehicle.type === "parachute" ? 22000 : 15000;
        vehicle.nextAppearance = time + rareDelay + Math.random() * randomDelay;
      }
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
      if (weatherMode === "mist") {
        particle.x += particle.horizontalSpeed * particle.flightDirection;
        particle.y += particle.verticalDrift + Math.sin(particle.x * .018 + particle.bob) * .24;
      } else {
        particle.y += particle.speed * particle.direction;
        particle.x += particle.drift + Math.sin(particle.y * .015 + particle.bob) * .18;
      }
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
        const birdSize = 3.5 + particle.size * 2.2;
        const wingPhase = particle.y * .055 + particle.bob;
        drawHummingbird(
          particle.x,
          particle.y,
          birdSize,
          particle.verticalDrift * .28 + Math.sin(wingPhase * .32) * .035,
          particle.alpha + .18,
          wingPhase,
          index,
          particle.flightDirection
        );
        if (index % 15 === 0) {
          const spacing = birdSize * 2.6;
          [
            [-particle.flightDirection * spacing, -spacing * .7],
            [-particle.flightDirection * spacing, spacing * .7],
            [-particle.flightDirection * spacing * 2, -spacing * 1.4],
            [-particle.flightDirection * spacing * 2, spacing * 1.4]
          ].forEach(([offsetX, offsetY], flockIndex) => {
            drawHummingbird(
              particle.x + offsetX,
              particle.y + offsetY,
              birdSize * (.78 + flockIndex * .035),
              particle.verticalDrift * .24 + Math.sin(wingPhase * .32) * .028,
              particle.alpha + .12,
              wingPhase + flockIndex * .7,
              index + flockIndex + 1,
              particle.flightDirection
            );
          });
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
    drawAerialVehicles(time);
    requestAnimationFrame(animate);
  }

  resize();
  window.addEventListener("resize", resize, { passive: true });
  requestAnimationFrame(animate);
});
