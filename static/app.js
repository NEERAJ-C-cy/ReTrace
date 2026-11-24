document.addEventListener("DOMContentLoaded", () => {
  const input = document.querySelector("#media");
  if (input) {
    const drop = document.querySelector("#dropzone");
    const preview = document.querySelector("#preview");
    const form = document.querySelector("#upload-form");
    const submit = document.querySelector("#submit-btn");

    const show = (file) => {
      preview.innerHTML = "";
      if (!file) return;
      const url = URL.createObjectURL(file);
      const el = document.createElement(file.type.startsWith("video/") ? "video" : "img");
      el.src = url;
      if (el.tagName === "VIDEO") el.controls = true;
      preview.appendChild(el);
      document.querySelector("#file-name").textContent =
        `${file.name} (${(file.size / 1048576).toFixed(1)} MB)`;
    };

    input.addEventListener("change", () => show(input.files[0]));

    ["dragenter", "dragover"].forEach((ev) =>
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.add("over");
      })
    );

    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.remove("over");
      })
    );

    drop.addEventListener("drop", (e) => {
      if (e.dataTransfer.files.length) {
        input.files = e.dataTransfer.files;
        show(input.files[0]);
      }
    });

    form.addEventListener("submit", () => {
      submit.disabled = true;
      submit.textContent = "Uploading...";
    });
  }

  const historicalInput = document.querySelector("#historical-media");
  if (historicalInput) {
    const count = document.querySelector("#historical-file-count");
    historicalInput.addEventListener("change", () => {
      const total = historicalInput.files.length;
      count.textContent = total
        ? `${total} file${total === 1 ? "" : "s"} selected for import`
        : "";
    });

    const adminForm = historicalInput.closest("form");
    adminForm.addEventListener("submit", () => {
      const submit = adminForm.querySelector("button[type='submit']");
      submit.disabled = true;
      submit.textContent = "Adding and fingerprinting...";
    });
  }

  const slider = document.querySelector("#overlay-slider");
  if (slider) {
    slider.addEventListener("input", () => {
      document.querySelector("#overlay-top").style.opacity = slider.value / 100;
    });
  }

  const filter = document.querySelector("#history-filter");
  if (filter) {
    filter.addEventListener("input", () => {
      const q = filter.value.toLowerCase();
      document.querySelectorAll("#history-table tbody tr").forEach((tr) => {
        tr.hidden = !tr.textContent.toLowerCase().includes(q);
      });
    });
  }
});
