document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-ai-composer]");
    const textarea = form?.querySelector("textarea");
    if (!form || !textarea) return;

    const status = form.querySelector("[data-ai-status]");
    const submit = form.querySelector('button[type="submit"]');

    const resizeInput = () => {
        textarea.style.height = "auto";
        textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
    };

    textarea.addEventListener("input", resizeInput);
    resizeInput();

    document.querySelectorAll("[data-ai-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            textarea.value = button.dataset.aiPrompt || "";
            textarea.focus();
            resizeInput();
        });
    });

    textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    form.addEventListener("submit", () => {
        if (!textarea.value.trim()) return;
        if (status) status.textContent = "Preparing your answer…";
        if (submit) {
            submit.disabled = true;
            submit.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin" aria-hidden="true"></i><span class="sr-only">Sending question</span>';
        }
    });

    const conversation = document.querySelector(".ai-conversation");
    if (conversation) conversation.scrollTop = conversation.scrollHeight;
});
