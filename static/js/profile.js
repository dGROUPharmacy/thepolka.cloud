(() => {
  const services = [
    ["GitHub","Developer portfolio and repositories","developer","https://github.com/signup"],
    ["Docker Hub","Container publishing and collaboration","developer","https://hub.docker.com/signup"],
    ["Salesforce Trailhead","Skills, badges and learning profile","career","https://trailhead.salesforce.com/"],
    ["Credly","Verified credential portfolio","career","https://info.credly.com/users/sign_up"],
    ["Google Scholar","Research author profile","career","https://scholar.google.com/"],
    ["LinkedIn","Professional identity and recruiting","career","https://www.linkedin.com/signup"],
    ["X / Twitter","Public updates and professional voice","creator","https://x.com/i/flow/signup"],
    ["Instagram","Visual portfolio and community","creator","https://www.instagram.com/accounts/emailsignup/"],
    ["Twitch","Live streaming and creator community","creator","https://www.twitch.tv/signup"],
    ["YouTube","Video publishing through a Google account","creator","https://www.youtube.com/"],
    ["Kaggle","Data science portfolio and competitions","developer","https://www.kaggle.com/"],
    ["Hugging Face","Models, datasets and AI demos","developer","https://huggingface.co/join"]
  ];
  const selected = new Set(), container = document.querySelector("#pk-services"), form = document.querySelector("#pk-form"), count = document.querySelector("#pk-count");
  function updateCount(){ count.textContent = `${selected.size} service${selected.size === 1 ? "" : "s"} selected`; }
  function render(filter = "all"){
    container.innerHTML = "";
    services.forEach(([name, desc, category], index) => {
      if (filter !== "all" && filter !== category) return;
      const card = document.createElement("article");
      card.className = `pk-service ${selected.has(index) ? "selected" : ""}`;
      card.tabIndex = 0;
      card.innerHTML = `<small>${category}</small><h3>${name}</h3><p>${desc}</p>`;
      const toggle = () => { selected.has(index) ? selected.delete(index) : selected.add(index); render(filter); updateCount(); };
      card.addEventListener("click", toggle);
      card.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); } });
      container.append(card);
    });
  }
  document.querySelectorAll(".pk-filter").forEach(button => button.addEventListener("click", () => {
    document.querySelectorAll(".pk-filter").forEach(item => item.classList.remove("active"));
    button.classList.add("active"); render(button.dataset.filter);
  }));
  document.querySelector("#pk-save").addEventListener("click", () => {
    if (!form.reportValidity()) return;
    localStorage.setItem("thepolka-profile-key", JSON.stringify(Object.fromEntries(new FormData(form))));
    document.querySelector("#pk-save").textContent = "Saved on this device";
  });
  document.querySelector("#pk-clear").addEventListener("click", () => {
    localStorage.removeItem("thepolka-profile-key"); form.reset(); selected.clear(); render(); updateCount();
  });
  document.querySelector("#pk-launch").addEventListener("click", () => {
    if (!selected.size) { alert("Choose at least one service first."); return; }
    if (!form.reportValidity()) return;
    if (!confirm("Open the selected official signup pages? You will review and submit each account yourself.")) return;
    [...selected].forEach(index => window.open(services[index][3], "_blank", "noopener,noreferrer"));
  });
  try {
    const saved = JSON.parse(localStorage.getItem("thepolka-profile-key"));
    if (saved) Object.entries(saved).forEach(([key, value]) => { if (form.elements[key]) form.elements[key].value = value; });
  } catch {}
  render(); updateCount();
})();
