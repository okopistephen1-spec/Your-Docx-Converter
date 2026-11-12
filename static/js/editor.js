const CONFIG = window.APP_CONFIG || { apiBaseUrl: window.location.origin || 'https://your-render-backend.onrender.com' };
const API_BASE_URL = (CONFIG.apiBaseUrl || window.location.origin || '').replace(/\/$/, '');

const emptyState = document.getElementById('emptyState');
const editorWorkspace = document.getElementById('editorWorkspace');
const editorFileInput = document.getElementById('editorFileInput');
const uploadDropzone = document.getElementById('uploadDropzone');
const browseEditorFile = document.getElementById('browseEditorFile');
const documentPage = document.getElementById('documentPage');
const saveStatus = document.getElementById('saveStatus');
const documentFilename = document.getElementById('documentFilename');
const saveDocumentBtn = document.getElementById('saveDocumentBtn');
const downloadDocumentBtn = document.getElementById('downloadDocumentBtn');
const findTextInput = document.getElementById('findTextInput');
const replaceTextInput = document.getElementById('replaceTextInput');
const fontSizeSelect = document.getElementById('fontSizeSelect');
const fontNameSelect = document.getElementById('fontNameSelect');
const alignmentSelect = document.getElementById('alignmentSelect');
const replaceTextBtn = document.getElementById('replaceTextBtn');
const replaceAllBtn = document.getElementById('replaceAllBtn');
const addParagraphBtn = document.getElementById('addParagraphBtn');
const deleteParagraphBtn = document.getElementById('deleteParagraphBtn');
const addTableRowBtn = document.getElementById('addTableRowBtn');
const deleteTableRowBtn = document.getElementById('deleteTableRowBtn');
const addTableColumnBtn = document.getElementById('addTableColumnBtn');
const deleteTableColumnBtn = document.getElementById('deleteTableColumnBtn');

const state = {
    filename: '',
    document: { paragraphs: [], tables: [] },
    selectedParagraphIndex: null,
    selectedTableIndex: null,
    selectedRowIndex: null,
    selectedCellIndex: null,
};

function apiUrl(path) {
    return `${API_BASE_URL}${path}`;
}

function getSessionToken() {
    return sessionStorage.getItem('docx_editor_token');
}

function authHeaders(extra = {}) {
    const token = getSessionToken();
    return {
        ...extra,
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
}

function getSelectedParagraphIndex() {
    return state.selectedParagraphIndex;
}

function showStatus(message, type = 'neutral') {
    saveStatus.textContent = message;
    saveStatus.className = `save-status ${type}`;
}

function showNotification(message, type = 'success') {
    showStatus(message, type);
    window.clearTimeout(showNotification.timeoutId);
    showNotification.timeoutId = window.setTimeout(() => {
        showStatus('Ready', 'neutral');
    }, 1800);
}

function setDocumentVisibility(hasDocument) {
    emptyState.classList.toggle('hidden', hasDocument);
    editorWorkspace.classList.toggle('hidden', !hasDocument);
}

function setFilename(name) {
    state.filename = name || 'No document open';
    documentFilename.textContent = state.filename;
}

function renderDocument(documentData) {
    state.document = documentData || { paragraphs: [], tables: [] };
    documentPage.innerHTML = '';

    if (!state.document.paragraphs.length && !state.document.tables.length) {
        documentPage.innerHTML = '<p class="doc-empty">No document content found.</p>';
        return;
    }

    state.document.paragraphs.forEach((paragraph) => {
        const paragraphEl = document.createElement('div');
        paragraphEl.className = 'doc-paragraph';
        paragraphEl.dataset.paragraphIndex = paragraph.index;
        paragraphEl.contentEditable = true;
        paragraphEl.textContent = paragraph.text || '';

        paragraphEl.addEventListener('focus', () => {
            state.selectedParagraphIndex = Number(paragraph.index);
            state.selectedTableIndex = null;
            state.selectedRowIndex = null;
            state.selectedCellIndex = null;
            document.querySelectorAll('.toolbar-button').forEach((button) => {
                button.classList.remove('is-active');
            });
        });

        paragraphEl.addEventListener('blur', () => {
            const nextText = paragraphEl.textContent.trim();
            persistParagraphUpdate(Number(paragraph.index), nextText);
        });

        documentPage.appendChild(paragraphEl);
    });

    state.document.tables.forEach((table) => {
        const wrapper = document.createElement('div');
        wrapper.className = 'doc-table-wrap';

        const tableEl = document.createElement('table');
        tableEl.className = 'doc-table';
        tableEl.dataset.tableIndex = table.index;

        table.rows.forEach((row, rowIndex) => {
            const tr = document.createElement('tr');
            row.forEach((cellValue, cellIndex) => {
                const td = document.createElement('td');
                const input = document.createElement('div');
                input.className = 'doc-cell';
                input.contentEditable = true;
                input.dataset.tableIndex = table.index;
                input.dataset.rowIndex = rowIndex;
                input.dataset.cellIndex = cellIndex;
                input.textContent = cellValue || '';

                input.addEventListener('focus', () => {
                    state.selectedTableIndex = Number(table.index);
                    state.selectedRowIndex = Number(rowIndex);
                    state.selectedCellIndex = Number(cellIndex);
                    state.selectedParagraphIndex = null;
                });

                input.addEventListener('blur', () => {
                    persistTableCellUpdate(
                        Number(table.index),
                        Number(rowIndex),
                        Number(cellIndex),
                        input.textContent
                    );
                });

                td.appendChild(input);
                tr.appendChild(td);
            });
            tableEl.appendChild(tr);
        });

        wrapper.appendChild(tableEl);
        documentPage.appendChild(wrapper);
    });
}

function fetchJson(url, options = {}) {
    return fetch(url, options).then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || 'Request failed.');
        }
        return data;
    });
}

function persistParagraphUpdate(index, text) {
    if (index === null || Number.isNaN(index)) {
        return;
    }

    const payload = {
        action: 'paragraph',
        paragraph_action: 'update',
        paragraph_index: index,
        text: text,
    };

    return fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(payload),
    }).then(() => {
        showStatus('Saved', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function persistTableCellUpdate(tableIndex, rowIndex, cellIndex, text) {
    return fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'table',
            table_action: 'update_cell',
            table_index: tableIndex,
            row_index: rowIndex,
            cell_index: cellIndex,
            text,
        }),
    }).then(() => {
        showStatus('Saved', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function handleDocumentUpload(file) {
    if (!file) {
        return;
    }

    if (!file.name.toLowerCase().endsWith('.docx')) {
        showNotification('Please upload a DOCX file.', 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    showStatus('Uploading...', 'neutral');

    fetch(apiUrl('/api/editor/upload'), {
        method: 'POST',
        body: formData,
        headers: authHeaders(),
    }).then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || 'Upload failed.');
        }

        if (data.token) {
            sessionStorage.setItem('docx_editor_token', data.token);
        }

        setFilename(data.filename);
        setDocumentVisibility(true);
        renderDocument(data.document);
        showNotification('Document loaded', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function getFormattingState() {
    const styles = { bold: false, italic: false, underline: false };

    document.querySelectorAll('[data-format]').forEach((button) => {
        const formatName = button.dataset.format;
        if (styleNameMap[formatName]) {
            styles[formatName] = button.classList.contains('is-active');
        }
    });

    if (fontSizeSelect.value) {
        styles.font_size = Number(fontSizeSelect.value);
    }

    if (fontNameSelect.value) {
        styles.font_name = fontNameSelect.value;
    }

    if (alignmentSelect.value) {
        styles.alignment = alignmentSelect.value;
    }

    return styles;
}

const styleNameMap = { bold: 'bold', italic: 'italic', underline: 'underline' };

function applyFormatSelection(format) {
    const paragraphIndex = getSelectedParagraphIndex();
    if (paragraphIndex === null || Number.isNaN(paragraphIndex)) {
        showNotification('Select a paragraph to format.', 'error');
        return;
    }

    const button = document.querySelector(`[data-format="${format}"]`);
    const nextValue = !(button && button.classList.contains('is-active'));

    if (button) {
        button.classList.toggle('is-active', nextValue);
    }

    applyCurrentFormatting();
}

function applyCurrentFormatting() {
    const paragraphIndex = getSelectedParagraphIndex();
    if (paragraphIndex === null || Number.isNaN(paragraphIndex)) {
        showNotification('Select a paragraph to format.', 'error');
        return;
    }

    const nextPayload = {
        action: 'paragraph',
        paragraph_action: 'format',
        paragraph_index: paragraphIndex,
        ...getFormattingState(),
    };

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(nextPayload),
    }).then(() => {
        showStatus('Formatting saved', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function replaceCurrentText(replaceAll = false) {
    const findText = findTextInput.value;
    const replaceText = replaceTextInput.value;

    if (!findText) {
        showNotification('Enter text to find first.', 'error');
        return;
    }

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'replace',
            find_text: findText,
            replace_text: replaceText,
            replace_all: replaceAll,
        }),
    }).then((payload) => {
        showNotification(replaceAll ? `Replaced ${payload.count} matches` : `Replaced ${payload.count} match`, 'success');
        return fetchJson(apiUrl('/api/editor/document'), { headers: authHeaders() });
    }).then((data) => {
        renderDocument(data.document);
        showStatus('Document updated', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function addParagraph() {
    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'paragraph',
            paragraph_action: 'add',
            text: 'New paragraph',
        }),
    }).then((data) => {
        state.selectedParagraphIndex = data.document.paragraphs.length - 1;
        renderDocument(data.document);
        showNotification('Paragraph added', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function deleteSelectedParagraph() {
    if (state.selectedParagraphIndex === null) {
        showNotification('Select a paragraph to delete.', 'error');
        return;
    }

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'paragraph',
            paragraph_action: 'delete',
            paragraph_index: state.selectedParagraphIndex,
        }),
    }).then((data) => {
        state.selectedParagraphIndex = null;
        renderDocument(data.document);
        showNotification('Paragraph removed', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function addTableRow() {
    const tableIndex = state.selectedTableIndex ?? 0;

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'table',
            table_action: 'add_row',
            table_index: tableIndex,
            values: ['New row item'],
        }),
    }).then((data) => {
        renderDocument(data.document);
        showNotification('Table row added', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function deleteSelectedTableRow() {
    const tableIndex = state.selectedTableIndex ?? 0;

    if (state.selectedRowIndex === null) {
        showNotification('Select a table cell first.', 'error');
        return;
    }

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'table',
            table_action: 'delete_row',
            table_index: tableIndex,
            row_index: state.selectedRowIndex,
        }),
    }).then((data) => {
        renderDocument(data.document);
        showNotification('Table row deleted', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function addTableColumn() {
    const tableIndex = state.selectedTableIndex ?? 0;

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'table',
            table_action: 'add_column',
            table_index: tableIndex,
            values: ['New column'],
        }),
    }).then((data) => {
        renderDocument(data.document);
        showNotification('Table column added', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function deleteSelectedTableColumn() {
    const tableIndex = state.selectedTableIndex ?? 0;

    if (state.selectedCellIndex === null) {
        showNotification('Select a table cell first.', 'error');
        return;
    }

    fetchJson(apiUrl('/api/editor/action'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
            action: 'table',
            table_action: 'delete_column',
            table_index: tableIndex,
            column_index: state.selectedCellIndex,
        }),
    }).then((data) => {
        renderDocument(data.document);
        showNotification('Table column deleted', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function saveDocument() {
    fetchJson(apiUrl('/api/editor/save'), {
        method: 'POST',
        headers: authHeaders(),
    }).then((response) => {
        setFilename(response.filename);
        showNotification('Document saved', 'success');
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

function downloadDocument() {
    if (!state.filename || state.filename === 'No document open') {
        showNotification('Open a document before downloading.', 'error');
        return;
    }

    fetch(apiUrl('/api/editor/download'), {
        headers: authHeaders(),
    }).then(async (response) => {
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.error || 'Download failed.');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const contentDisposition = response.headers.get('Content-Disposition') || '';
        const filenameMatch = /filename\*=UTF-8''(.+)|filename="?(.+?)"?/.exec(contentDisposition);
        const filename = decodeURIComponent((filenameMatch && (filenameMatch[1] || filenameMatch[2])) || state.filename || 'document.docx');

        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }).catch((error) => {
        showNotification(error.message, 'error');
    });
}

browseEditorFile.addEventListener('click', () => {
    editorFileInput.click();
});

uploadDropzone.addEventListener('click', () => {
    editorFileInput.click();
});

uploadDropzone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        editorFileInput.click();
    }
});

editorFileInput.addEventListener('change', (event) => {
    const [file] = event.target.files;
    handleDocumentUpload(file);
    event.target.value = '';
});

['dragenter', 'dragover'].forEach((eventName) => {
    uploadDropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        uploadDropzone.classList.add('is-dragging');
    });
});

['dragleave', 'drop'].forEach((eventName) => {
    uploadDropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        uploadDropzone.classList.remove('is-dragging');
    });
});

uploadDropzone.addEventListener('drop', (event) => {
    const file = event.dataTransfer.files && event.dataTransfer.files[0];
    handleDocumentUpload(file);
});

document.addEventListener('click', (event) => {
    const formatButton = event.target.closest('[data-format]');
    if (formatButton) {
        applyFormatSelection(formatButton.dataset.format);
    }
});

saveDocumentBtn.addEventListener('click', saveDocument);
downloadDocumentBtn.addEventListener('click', downloadDocument);
replaceTextBtn.addEventListener('click', () => replaceCurrentText(false));
replaceAllBtn.addEventListener('click', () => replaceCurrentText(true));
addParagraphBtn.addEventListener('click', addParagraph);
deleteParagraphBtn.addEventListener('click', deleteSelectedParagraph);
addTableRowBtn.addEventListener('click', addTableRow);
deleteTableRowBtn.addEventListener('click', deleteSelectedTableRow);
addTableColumnBtn.addEventListener('click', addTableColumn);
deleteTableColumnBtn.addEventListener('click', deleteSelectedTableColumn);

saveDocumentBtn.addEventListener('click', saveDocument);
downloadDocumentBtn.addEventListener('click', downloadDocument);
replaceTextBtn.addEventListener('click', () => replaceCurrentText(false));
replaceAllBtn.addEventListener('click', () => replaceCurrentText(true));
addParagraphBtn.addEventListener('click', addParagraph);
deleteParagraphBtn.addEventListener('click', deleteSelectedParagraph);
addTableRowBtn.addEventListener('click', addTableRow);
deleteTableRowBtn.addEventListener('click', deleteSelectedTableRow);
addTableColumnBtn.addEventListener('click', addTableColumn);
deleteTableColumnBtn.addEventListener('click', deleteSelectedTableColumn);

fontSizeSelect.addEventListener('change', () => {
    const selectedIndex = getSelectedParagraphIndex();
    if (selectedIndex === null) {
        showNotification('Select a paragraph first.', 'error');
        return;
    }

    applyCurrentFormatting();
});

fontNameSelect.addEventListener('change', () => {
    const selectedIndex = getSelectedParagraphIndex();
    if (selectedIndex === null) {
        showNotification('Select a paragraph first.', 'error');
        return;
    }

    applyCurrentFormatting();
});

alignmentSelect.addEventListener('change', () => {
    const selectedIndex = getSelectedParagraphIndex();
    if (selectedIndex === null) {
        showNotification('Select a paragraph first.', 'error');
        return;
    }

    applyCurrentFormatting();
});

showStatus('Ready', 'neutral');
setDocumentVisibility(false);
