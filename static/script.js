(function () {
  const mobileNavToggle = document.querySelector('.mobile-nav-toggle');
  const navMenu = document.querySelector('.nav-menu');
  if (mobileNavToggle && navMenu) {
    mobileNavToggle.addEventListener('click', () => {
      const isOpen = navMenu.classList.toggle('is-open');
      mobileNavToggle.setAttribute('aria-expanded', String(isOpen));
    });
    navMenu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
      navMenu.classList.remove('is-open');
      mobileNavToggle.setAttribute('aria-expanded', 'false');
    }));
  }

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

  const cartKey = 'fis-cart';
  const readCart = () => {
    try { return JSON.parse(localStorage.getItem(cartKey) || '[]'); } catch { return []; }
  };
  const updateCartCount = () => {
    const count = readCart().reduce((total, item) => total + (item.quantity || 1), 0);
    document.querySelectorAll('[data-cart-count]').forEach((node) => {
      node.textContent = count;
      node.hidden = count === 0;
    });
  };
  updateCartCount();

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
    const picker = document.querySelector('[data-color-picker]');
    const selection = document.querySelector('[data-detail-selection]');
    const note = document.querySelector('[data-cart-note]');
    const variants = product.variants || [{ color: '', images: [] }];
    const frames = variants.flatMap((variant, variantIndex) =>
      (variant.images || []).map((src) => ({ src, color: variant.color || '', variantIndex }))
    );
    let frameIndex = 0;
    const assetSrc = (src) => src.startsWith('media/') ? `/media/${src.slice(6)}` : `/static/${src}`;
    function render() {
      const selected = frames[frameIndex];
      const source = selected ? assetSrc(selected.src) : '';
      detailImage.hidden = !source;
      placeholder.hidden = !!source;
      if (source) detailImage.src = source;
      selection.textContent = selected && selected.color ? `Color: ${selected.color}` : '';
    }
    if (variants.length > 1) {
      picker.innerHTML = variants.map((v, i) => `<button type="button" class="${i === 0 ? 'active' : ''}" data-variant-index="${i}">${v.color || 'Default'}</button>`).join('');
      picker.querySelectorAll('button').forEach(btn => btn.addEventListener('click', () => {
        const index = Number(btn.dataset.variantIndex);
        frameIndex = Math.max(0, frames.findIndex((frame) => frame.variantIndex === index));
        picker.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b === btn));
        render();
      }));
    }
    document.querySelector('[data-add-cart]').addEventListener('click', () => {
      fetch('/store/cart/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
        .then(async (response) => {
          const result = await response.json();
          if (!response.ok) throw new Error(result.message || 'Unable to add this item.');
          const cart = readCart();
          const color = frames[frameIndex]?.color || '';
          const image = frames[frameIndex]?.src || '';
          const existing = cart.find((item) => item.name === product.name && item.color === color && item.image === image);
          if (existing) existing.quantity = (existing.quantity || 1) + 1;
          else cart.push({ name: product.name, price: product.price, color, image, quantity: 1 });
          localStorage.setItem(cartKey, JSON.stringify(cart));
          updateCartCount();
          note.textContent = `${product.name}${color ? ` — ${color}` : ''} saved to your cart.`;
        })
        .catch((error) => { note.textContent = error.message; });
    });
    render();
  }

  const cartItems = document.querySelector('[data-cart-items]');
  if (cartItems) {
    const cart = readCart();
    const empty = document.querySelector('[data-cart-empty]');
    const checkoutNote = document.querySelector('[data-cart-checkout]');
    if (cart.length) {
      empty.hidden = true;
      checkoutNote.hidden = false;
      cartItems.innerHTML = cart.map((item, index) => `
        <article class="cart-item">
          ${item.image ? `<img src="${item.image.startsWith('media/') ? `/media/${item.image.slice(6)}` : `/static/${item.image}`}" alt="">` : '<div class="cart-item-placeholder">FIS</div>'}
          <div><h2>${item.name.toUpperCase()}</h2><p>${item.color || 'Default'} · ${item.price}</p></div>
          <strong>${item.quantity || 1}</strong>
          <button type="button" data-remove-cart="${index}">Remove</button>
        </article>`).join('');
      cartItems.querySelectorAll('[data-remove-cart]').forEach((button) => button.addEventListener('click', () => {
        const next = readCart();
        next.splice(Number(button.dataset.removeCart), 1);
        localStorage.setItem(cartKey, JSON.stringify(next));
        window.location.reload();
      }));
    }
  }
})();
