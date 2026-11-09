document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('app-sidebar');
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    if (sidebar && sidebarToggle) {
        sidebarToggle.addEventListener('click', () => {
            const isOpen = sidebar.classList.toggle('open');
            sidebarToggle.setAttribute('aria-expanded', String(isOpen));
        });
    }

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileListContainer = document.getElementById('file-list-container');
    const fileList = document.getElementById('file-list');
    const fileCount = document.getElementById('file-count');
    const clearBtn = document.getElementById('clear-btn');
    const uploadForm = document.getElementById('upload-form');
    const loading = document.getElementById('loading');

    if (!dropZone || !fileInput) return;

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#16a34a';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.style.borderColor = '#2563eb';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#2563eb';
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            updateFileList();
        }
    });

    fileInput.addEventListener('change', updateFileList);

    function updateFileList() {
        fileList.innerHTML = '';
        const files = Array.from(fileInput.files);
        fileCount.textContent = files.length;
        if (files.length > 0) {
            fileListContainer.style.display = 'block';
            files.forEach(f => {
                const li = document.createElement('li');
                li.textContent = `${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
                fileList.appendChild(li);
            });
        } else {
            fileListContainer.style.display = 'none';
        }
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            fileInput.value = '';
            updateFileList();
        });
    }

    if (uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!fileInput.files.length) return;

            const formData = new FormData();
            Array.from(fileInput.files).forEach(f => formData.append('files', f));

            dropZone.style.display = 'none';
            fileListContainer.style.display = 'none';
            loading.style.display = 'block';

            try {
                const res = await fetch('/upload', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    window.location.href = '/results';
                } else {
                    alert('Error: ' + data.error);
                    location.reload();
                }
            } catch (err) {
                alert('Upload failed: ' + err.message);
                location.reload();
            }
        });
    }
});