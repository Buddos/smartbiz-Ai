document.addEventListener('DOMContentLoaded', () => {
    const shell = document.querySelector('.salon-shell');
    const menuButton = document.querySelector('[data-salon-menu]');
    const closeTargets = document.querySelectorAll('[data-salon-close]');

    if (!shell || !menuButton) return;

    const setMenuOpen = (isOpen) => {
        shell.classList.toggle('salon-menu-open', isOpen);
        menuButton.setAttribute('aria-expanded', String(isOpen));
        menuButton.setAttribute('aria-label', isOpen ? 'Close navigation' : 'Open navigation');
    };

    menuButton.addEventListener('click', () => {
        setMenuOpen(!shell.classList.contains('salon-menu-open'));
    });

    closeTargets.forEach((target) => {
        target.addEventListener('click', () => setMenuOpen(false));
    });

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') setMenuOpen(false);
    });

    document.querySelectorAll('[data-account-menu]').forEach((menu) => {
        const button = menu.querySelector('[data-account-menu-button]');
        const popover = menu.querySelector('[data-account-menu-popover]');
        if (!button || !popover) return;
        button.addEventListener('click', () => {
            const isOpen = popover.classList.toggle('is-open');
            button.setAttribute('aria-expanded', String(isOpen));
        });
        document.addEventListener('click', (event) => {
            if (!menu.contains(event.target)) {
                popover.classList.remove('is-open');
                button.setAttribute('aria-expanded', 'false');
            }
        });
    });

    const liveRefresh = document.querySelector('[data-salon-live-refresh]');
    const refreshDelay = Number(liveRefresh?.dataset.salonLiveRefresh);
    if (liveRefresh && Number.isFinite(refreshDelay) && refreshDelay > 0) {
        const refreshWhenIdle = () => {
            const activeElement = document.activeElement;
            const editingForm = activeElement instanceof HTMLElement
                && activeElement.closest('form');
            if (document.hidden || editingForm) {
                window.setTimeout(refreshWhenIdle, 5000);
                return;
            }
            window.location.reload();
        };
        window.setTimeout(refreshWhenIdle, refreshDelay);
    }
});
