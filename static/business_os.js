(() => {
  const button = document.querySelector('.bos-menu');
  const sidebar = document.getElementById('businessOsSidebar');
  if (!button || !sidebar) return;
  const close = () => { sidebar.classList.remove('open'); button.setAttribute('aria-expanded', 'false'); };
  button.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open');
    button.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  sidebar.addEventListener('click', event => { if (event.target.closest('a') && window.innerWidth <= 820) close(); });
})();
