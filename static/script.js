(function () {
  const revealTargets = document.querySelectorAll(
    '.page-section > *, .landing-hero, .landing-page > section, ' +
    '.landing-page .social-link, .landing-page .feature-image, ' +
    '.events-section, .member-card, .bio-content, .songs-list, .slideshow'
  );

  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && revealTargets.length) {
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12 });

    revealTargets.forEach((element, index) => {
      element.classList.add('reveal-on-scroll');
      element.style.setProperty('--reveal-delay', `${Math.min(index * 45, 240)}ms`);
      revealObserver.observe(element);
    });
  }

  const slides = document.querySelectorAll('.slide');
  const dots = document.querySelectorAll('.dot');
  const prevBtn = document.querySelector('.slide-btn.prev');
  const nextBtn = document.querySelector('.slide-btn.next');
  let current = 0;
  let timer;

  function show(index) {
    if (!slides.length) return;
    slides.forEach((s, i) => s.classList.toggle('active', i === index));
    dots.forEach((d, i) => d.classList.toggle('active', i === index));
    current = index;
  }

  function next() {
    if (!slides.length) return;
    show((current + 1) % slides.length);
  }

  function prev() {
    if (!slides.length) return;
    show((current - 1 + slides.length) % slides.length);
  }

  function restart() {
    clearInterval(timer);
    timer = setInterval(next, 5000);
  }

  if (nextBtn) nextBtn.addEventListener('click', () => { next(); restart(); });
  if (prevBtn) prevBtn.addEventListener('click', () => { prev(); restart(); });
  dots.forEach((dot) => {
    dot.addEventListener('click', () => {
      show(parseInt(dot.dataset.index, 10));
      restart();
    });
  });

  if (slides.length > 1) restart();

  document.querySelectorAll('[data-card-product]').forEach((card) => {
    const product = JSON.parse(card.dataset.cardProduct);
    const image = card.querySelector('[data-card-image]');
    const color = card.querySelector('[data-card-color]');
    const variants = product.variants || [{ color: '', images: [] }];
    const frames = variants.flatMap((variant, variantIndex) =>
      (variant.images || []).map((src) => ({ src, color: variant.color || '', variantIndex }))
    );
    let frameIndex = 0;
    const assetSrc = (src) => src.startsWith('media/') ? `/media/${src.slice(6)}` : `/static/${src}`;
    function renderCard() {
      if (!image || !frames.length) return;
      image.src = assetSrc(frames[frameIndex].src);
      image.alt = `${product.name}${frames[frameIndex].color ? ` — ${frames[frameIndex].color}` : ''}`;
      if (color) color.textContent = frames[frameIndex].color;
    }
    const move = (amount) => { if (frames.length) { frameIndex = (frameIndex + amount + frames.length) % frames.length; renderCard(); } };
    card.querySelector('[data-card-prev]')?.addEventListener('click', (event) => { event.preventDefault(); move(-1); });
    card.querySelector('[data-card-next]')?.addEventListener('click', (event) => { event.preventDefault(); move(1); });
    let startX = 0;
    card.addEventListener('touchstart', (event) => { startX = event.changedTouches[0].clientX; }, { passive: true });
    card.addEventListener('touchend', (event) => {
      const delta = event.changedTouches[0].clientX - startX;
      if (Math.abs(delta) > 35) move(delta < 0 ? 1 : -1);
    }, { passive: true });
  });

  const product = window.storeProduct;
  const detailImage = document.querySelector('[data-detail-image]');
  if (product && detailImage) {
    const placeholder = document.querySelector('[data-detail-placeholder]');
    const thumbs = document.querySelector('[data-detail-thumbs]');
    const picker = document.querySelector('[data-color-picker]');
    const selection = document.querySelector('[data-detail-selection]');
    const note = document.querySelector('[data-cart-note]');
    let variantIndex = 0;
    let imageIndex = 0;
    const variants = product.variants || [{ color: '', images: [] }];
    function currentImages() { return variants[variantIndex].images || []; }
    function render() {
      const images = currentImages();
      const source = images[imageIndex] ? (images[imageIndex].startsWith('media/') ? `/media/${images[imageIndex].slice(6)}` : `/static/${images[imageIndex]}`) : '';
      detailImage.hidden = !source;
      placeholder.hidden = !!source;
      if (source) detailImage.src = source;
      thumbs.innerHTML = images.map((src, i) => `<button type="button" class="${i === imageIndex ? 'active' : ''}" data-image-index="${i}"><img src="${src.startsWith('media/') ? `/media/${src.slice(6)}` : `/static/${src}`}" alt=""></button>`).join('');
      selection.textContent = variants[variantIndex].color ? `Color: ${variants[variantIndex].color}` : '';
      thumbs.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => { imageIndex = Number(btn.dataset.imageIndex); render(); }));
    }
    if (variants.length > 1) {
      picker.innerHTML = variants.map((v, i) => `<button type="button" class="${i === 0 ? 'active' : ''}" data-variant-index="${i}">${v.color || 'Default'}</button>`).join('');
      picker.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => { variantIndex = Number(btn.dataset.variantIndex); imageIndex = 0; picker.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn)); render(); }));
    }
    document.querySelector('.detail-prev').addEventListener('click', () => { const n = currentImages().length; if (n) { imageIndex = (imageIndex - 1 + n) % n; render(); } });
    document.querySelector('.detail-next').addEventListener('click', () => { const n = currentImages().length; if (n) { imageIndex = (imageIndex + 1) % n; render(); } });
    document.querySelector('[data-add-cart]').addEventListener('click', () => {
      note.textContent = `${product.name}${variants[variantIndex].color ? ` — ${variants[variantIndex].color}` : ''} saved to your cart.`;
    });
    render();
  }
})();
