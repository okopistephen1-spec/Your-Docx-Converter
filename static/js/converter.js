const CONFIG = window.APP_CONFIG || { apiBaseUrl: window.location.origin || 'https://your-render-backend.onrender.com' };
const API_BASE_URL = (CONFIG.apiBaseUrl || window.location.origin || '').replace(/\/$/, '');

const fileInput = document.getElementById('fileInput');
const converterForm = document.getElementById('converterForm');
const dropzone = document.getElementById('dropzone');
const browseButton = document.getElementById('browseButton');
const triggerFileInput = document.getElementById('triggerFileInput');
const convertFrom = document.getElementById('convertFrom');
const convertTo = document.getElementById('convertTo');
const swapFormats = document.getElementById('swapFormats');
const selectedFile = document.getElementById('selectedFile');
const selectedName = document.getElementById('selectedName');
const selectedSize = document.getElementById('selectedSize');
const removeFileButton = document.getElementById('removeFileButton');
const submitButton = document.getElementById('submitButton');
const quickPills = document.querySelectorAll('.quick-pill');

const conversionMap = {
  'pdf-docx': {
    route: '/api/convert/pdf-to-word',
    fileInputName: 'pdf_file',
    accept: '.pdf,application/pdf'
  },
  'pdf-png': {
    route: '/api/convert/pdf-to-images',
    fileInputName: 'pdf_file',
    accept: '.pdf,application/pdf'
  },
  'docx-pdf': {
    route: '/api/convert/word-to-pdf',
    fileInputName: 'word_file',
    accept: '.docx,.doc,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword'
  },
  'doc-pdf': {
    route: '/api/convert/word-to-pdf',
    fileInputName: 'word_file',
    accept: '.docx,.doc,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword'
  }
};

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

function formatBytes(bytes) {
  if (!bytes) {
    return '0 KB';
  }

  const units = ['Bytes', 'KB', 'MB', 'GB'];
  const power = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / (1024 ** power);
  const formatted = value >= 10 || power === 0 ? value.toFixed(0) : value.toFixed(1);

  return `${formatted} ${units[power]}`;
}

function updateSubmitState() {
  const fileSelected = Boolean(fileInput.files && fileInput.files[0]);
  const from = convertFrom.value;
  const to = convertTo.value;
  const validSelection = Boolean(conversionMap[`${from}-${to}`]);

  submitButton.disabled = !fileSelected || !validSelection;
}

function syncConversionSelection() {
  const from = convertFrom.value;
  const to = convertTo.value;

  const presetKey = `${from}-${to}`;
  const config = conversionMap[presetKey];

  if (!config) {
    updateSubmitState();
    quickPills.forEach((pill) => pill.classList.remove('is-active'));
    return;
  }

  converterForm.action = apiUrl(config.route);
  fileInput.name = config.fileInputName;
  fileInput.accept = config.accept;

  quickPills.forEach((pill) => {
    const matches = pill.dataset.from === from && pill.dataset.to === to;
    pill.classList.toggle('is-active', matches);
  });

  if (fileInput.files && fileInput.files[0]) {
    const selected = fileInput.files[0];
    selectedName.textContent = selected.name;
    selectedSize.textContent = formatBytes(selected.size);
    selectedFile.hidden = false;
  }

  updateSubmitState();
}

function applyPreset(from, to) {
  convertFrom.value = from;
  convertTo.value = to;
  syncConversionSelection();
}

function handleFileSelection(file) {
  if (!file) {
    selectedFile.hidden = true;
    selectedName.textContent = 'No file selected';
    selectedSize.textContent = '0 KB';
    updateSubmitState();
    return;
  }

  selectedName.textContent = file.name;
  selectedSize.textContent = formatBytes(file.size);
  selectedFile.hidden = false;
  updateSubmitState();
}

function downloadConvertedFile(response, fallbackName) {
  const contentDisposition = response.headers.get('Content-Disposition') || '';
  const filenameMatch = /filename\*=UTF-8''(.+)|filename="?(.+?)"?/.exec(contentDisposition);
  const suggestedName = decodeURIComponent((filenameMatch && (filenameMatch[1] || filenameMatch[2])) || fallbackName || 'converted-file');

  return response.blob().then((blob) => {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = suggestedName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  });
}

browseButton.addEventListener('click', () => fileInput.click());
triggerFileInput.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (event) => {
  const selectedFileItem = event.target.files && event.target.files[0];
  handleFileSelection(selectedFileItem);
});

removeFileButton.addEventListener('click', () => {
  fileInput.value = '';
  handleFileSelection(null);
});

['dragenter', 'dragover'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add('dragover');
  });
});

['dragleave', 'drop'].forEach((eventName) => {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove('dragover');
  });
});

dropzone.addEventListener('drop', (event) => {
  const droppedFiles = event.dataTransfer && event.dataTransfer.files;
  if (!droppedFiles || !droppedFiles.length) {
    return;
  }

  const [file] = droppedFiles;
  fileInput.files = droppedFiles;
  handleFileSelection(file);
});

dropzone.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    fileInput.click();
  }
});

swapFormats.addEventListener('click', () => {
  const previousFrom = convertFrom.value;
  convertFrom.value = convertTo.value;
  convertTo.value = previousFrom;
  syncConversionSelection();
});

convertFrom.addEventListener('change', syncConversionSelection);
convertTo.addEventListener('change', syncConversionSelection);

quickPills.forEach((pill) => {
  pill.addEventListener('click', () => {
    applyPreset(pill.dataset.from, pill.dataset.to);
  });
});

converterForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  if (!fileInput.files || !fileInput.files[0]) {
    return;
  }

  syncConversionSelection();

  const formData = new FormData();
  formData.append(fileInput.name, fileInput.files[0]);
  const route = converterForm.action || apiUrl(conversionMap[`${convertFrom.value}-${convertTo.value}`].route);
  submitButton.disabled = true;
  submitButton.textContent = 'Converting...';

  try {
    const response = await fetch(route, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const payload = await response.text();
      throw new Error(payload || 'Conversion failed.');
    }

    await downloadConvertedFile(response, `${selectedName.textContent || 'document'}`);
    submitButton.textContent = 'Convert Document';
    submitButton.disabled = false;
  } catch (error) {
    submitButton.textContent = 'Convert Document';
    submitButton.disabled = false;
    window.alert(error.message || 'Conversion failed. Please try again.');
  }
});

syncConversionSelection();
handleFileSelection(null);
