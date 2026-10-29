// Circuit Pathways home: drifting pixel squares, reveal-on-scroll, the class forms.
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const sky = $(".sky");
  const cols = ["#19c1ca", "#704988", "#cfc2e0", "#04bbc1", "#815a99"];
  for (let i = 0; i < 14; i++) {
    const s = 14 + Math.random() * 34, sq = document.createElement("i");
    sq.style.cssText = `left:${Math.random() * 100}%;top:${Math.random() * 100}%;width:${s}px;height:${s}px;background:${cols[i % 5]};` +
      `animation-delay:${-Math.random() * 20}s;animation-duration:${16 + Math.random() * 18}s`;
    sky.append(sq);
  }

  const revealer = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("in"); revealer.unobserve(e.target); }
  }), { threshold: 0.12 });
  $$(".reveal").forEach((el) => revealer.observe(el));
})();
