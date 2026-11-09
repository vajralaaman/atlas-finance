/**
 * Atlas Finance - shared client-side JavaScript
 * Client-side functionality for file handling and UI interactions
 */

// This file serves as a placeholder for shared JavaScript utilities.
// Most of the application logic is implemented directly in the templates
// to keep Phase 1 simple and beginner-friendly.

// Utility function to format file size
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Utility function to validate file type
function isValidPDFFile(file) {
    return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
}

// Utility function to escape HTML special characters
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Initialize document when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    // Any global initialization can go here
    // Currently, most functionality is in the template files
});

// Export functions for use in templates
window.fileUtils = {
    formatFileSize: formatFileSize,
    isValidPDFFile: isValidPDFFile,
    escapeHtml: escapeHtml
};
