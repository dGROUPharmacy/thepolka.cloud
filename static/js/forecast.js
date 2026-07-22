(() => {
  const summary=document.getElementById("forecast-summary"),discussion=document.getElementById("forecast-discussion"),issued=document.getElementById("forecast-issued"),satellite=document.getElementById("goes-image"),ad=document.getElementById("weather-ad");
  const track=event=>fetch("/api/forecast/ad-event",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({event}),keepalive:true}).catch(()=>{});
  track("impression"); ad.addEventListener("click",()=>track("click"));
  function speak(el,button){if(!("speechSynthesis" in window)){button.textContent="Speech unavailable";return}speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(el.textContent);u.rate=.96;button.textContent="■ Reading";u.onend=()=>button.textContent="▶ Read aloud";speechSynthesis.speak(u)}
  document.getElementById("read-forecast").addEventListener("click",e=>speak(summary,e.currentTarget));document.getElementById("read-discussion").addEventListener("click",e=>speak(discussion,e.currentTarget));
  async function loadForecast(){try{const r=await fetch("/api/forecast"),d=await r.json();if(!r.ok)throw new Error(d.error);const p=d.period;summary.textContent=`Forecast issued every 6 hours. ${p.name}. Temperature: ${p.temperature}°${p.temperatureUnit}. Wind: ${p.windSpeed}. Conditions: ${p.detailedForecast}`;discussion.textContent=d.discussion;issued.textContent="Last Updated: "+new Date().toLocaleString()}catch(e){summary.textContent="Forecast unavailable.";discussion.textContent=e.message||"Discussion unavailable."}}
  loadForecast();setInterval(loadForecast,21600000);setInterval(()=>satellite.src="https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/1250x750.jpg?t="+Date.now(),300000);
})();
