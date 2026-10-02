document.addEventListener("DOMContentLoaded", () => {
    const shell = document.querySelector(".electronics-app-shell");
    const openButton = document.querySelector("[data-electronics-open]");
    const closeButton = document.querySelector("[data-electronics-close]");

    if (!shell || !openButton || !closeButton) return;

    const setMenuOpen = (isOpen) => {
        shell.classList.toggle("nav-open", isOpen);
        openButton.setAttribute("aria-expanded", String(isOpen));
    };

    openButton.addEventListener("click", () => {
        setMenuOpen(!shell.classList.contains("nav-open"));
    });
    closeButton.addEventListener("click", () => setMenuOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setMenuOpen(false);
    });
});
