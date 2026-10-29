// The drifting squares behind the page, as on the home page.
const cols = ["#19c1ca", "#704988", "#cfc2e0", "#04bbc1", "#815a99"];
const sky = document.querySelector(".sky");
for (let i = 0; i < 10; i++) {
  const s = 14 + Math.random() * 30;
  const sq = document.createElement("i");
  sq.style.cssText = `left:${Math.random() * 100}%;top:${Math.random() * 100}%;width:${s}px;height:${s}px;background:${cols[i % 5]};animation-delay:${-Math.random() * 20}s;animation-duration:${16 + Math.random() * 18}s`;
  sky.append(sq);
}
