// Script principal de STOCKFLOW

// Mostrar notificaciones
function showNotification(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type === 'success' ? 'success' : 'danger'} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    const container = document.querySelector('main');
    if (container) {
        container.insertBefore(alertDiv, container.firstChild);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
}

// Formatear moneda
function formatCurrency(value) {
    return new Intl.NumberFormat('es-CO', {
        style: 'currency',
        currency: 'COP'
    }).format(value);
}

// Formatear fecha
function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('es-CO');
}

// Validar email
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

// Validar teléfono
function validatePhone(phone) {
    const re = /^[0-9]{7,15}$/;
    return re.test(phone);
}

// Cargar datos en tabla dinámica
function loadTableData(tableId, data, columns) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${columns.length + 1}" class="text-center text-muted">No hay datos</td></tr>`;
        return;
    }

    tbody.innerHTML = data.map(item => `
        <tr>
            ${columns.map(col => `<td>${item[col] || '-'}</td>`).join('')}
        </tr>
    `).join('');
}

// Confirmación de acción
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Limpiar formulario
function clearForm(formId) {
    const form = document.getElementById(formId);
    if (form) {
        form.reset();
    }
}

function cleanupModalResidues() {

    document.body.classList.remove('modal-open');

    document.querySelectorAll('.modal-backdrop')
        .forEach(backdrop => backdrop.remove());

    document.body.style.overflow = '';
    document.body.style.paddingRight = '';

    document.querySelectorAll('.modal.show')
        .forEach(modal => {
            modal.classList.remove('show');
            modal.style.display = 'none';
            modal.setAttribute('aria-hidden', 'true');
        });
}

// Ocultar modal
function hideModal(modalId) {
    const modalElement = document.getElementById(modalId);

    if (!modalElement) return;

    const bsModal =
        bootstrap.Modal.getInstance(modalElement) ||
        bootstrap.Modal.getOrCreateInstance(modalElement);

    bsModal.hide();

    setTimeout(() => {
        cleanupModalResidues();
    }, 350);
}

// Mostrar modal
function showModal(modalId) {
    const modalElement = document.getElementById(modalId);
    if (!modalElement) return;

    const bsModal = bootstrap.Modal.getInstance(modalElement) || bootstrap.Modal.getOrCreateInstance(modalElement);
    if (bsModal && typeof bsModal.show === 'function') {
        bsModal.show();
    }
}

function openFormModal(modalId) {
    cleanupModalResidues();
    const modalElement = document.getElementById(modalId);
    if (!modalElement) return;

    modalElement.querySelector('form')?.reset();
    bootstrap.Modal.getOrCreateInstance(modalElement, { backdrop: false }).show();
}

async function submitModalForm(event, options) {
    event.preventDefault();

    const form = event.currentTarget;
    if (!form.reportValidity()) return;

    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) submitButton.disabled = true;

    try {
        const response = await options.submit();
        const modalElement = document.getElementById(options.modalId);
        bootstrap.Modal.getOrCreateInstance(modalElement, { backdrop: false }).hide();
        await new Promise(resolve => setTimeout(resolve, 400));
        cleanupModalResidues();
        form.reset();

        if (options.onSuccess) await options.onSuccess(response);
        const message = typeof options.successMessage === 'function'
            ? options.successMessage(response)
            : options.successMessage;
        if (message) alert(message);
        return response;
    } catch (error) {
        alert(error.response?.data?.error || options.errorMessage || error.message || 'No se pudo guardar');
        return null;
    } finally {
        if (submitButton) submitButton.disabled = false;
    }
}

// Debounce para búsquedas
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Manejo de errores de API
function handleApiError(error) {
    if (error.response) {
        // El servidor respondió con un estado diferente a 2xx
        return error.response.data?.error || 'Error en el servidor';
    } else if (error.request) {
        // La solicitud fue hecha pero no se recibió respuesta
        return 'No se pudo conectar con el servidor';
    } else {
        // Algo sucedió en la configuración de la solicitud
        return error.message || 'Error desconocido';
    }
}

// Validar formulario antes de enviar
function validateForm(formData, rules) {
    for (const field in rules) {
        if (!formData[field]) {
            return `El campo ${rules[field]} es requerido`;
        }
    }
    return null;
}

// Exportar datos a CSV
function exportToCSV(filename, data) {
    let csv = 'data:text/csv;charset=utf-8,';
    
    if (data.length > 0) {
        // Encabezados
        csv += Object.keys(data[0]).join(',') + '\n';
        
        // Datos
        data.forEach(row => {
            csv += Object.values(row).map(val => `"${val}"`).join(',') + '\n';
        });
    }

    const encodedUri = encodeURI(csv);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `${filename}.csv`);
    document.body.appendChild(link);

    link.click();
    document.body.removeChild(link);
}

// El temporizador de inactividad se desactiva para evitar cierres de sesión
// inesperados que hacen parecer la interfaz congelada.

// Inicializar tooltips de Bootstrap
document.addEventListener('DOMContentLoaded', () => {
    const tabTokenKey = 'stockflow_tab_token';
    let tabToken = sessionStorage.getItem(tabTokenKey);
    if (!tabToken) {
        tabToken = Array.from(crypto.getRandomValues(new Uint8Array(32)), byte => byte.toString(16).padStart(2, '0')).join('');
        sessionStorage.setItem(tabTokenKey, tabToken);
    }
    if (window.axios) {
        axios.defaults.headers.common['X-Tab-Token'] = tabToken;
    }

    document.addEventListener('click', event => {
        const link = event.target.closest?.('a[href]');
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.hasAttribute('download')) return;
        if (link.target && link.target.toLowerCase() !== '_self') return;

        const destination = new URL(link.href, window.location.href);
        if (destination.origin !== window.location.origin) return;

        event.preventDefault();
        destination.searchParams.set('tab_token', tabToken);
        window.location.assign(destination.href);
    });

    // Activar tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl));

    // Activar popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(popoverTriggerEl => new bootstrap.Popover(popoverTriggerEl));

    // Mantener activo el enlace de navegación actual
    const currentLocation = location.pathname;
    const menuItems = document.querySelectorAll('.side-menu-links a');
    
    menuItems.forEach(item => {
        if (item.getAttribute('href') === currentLocation) {
            item.classList.add('active');
        }
    });

    const menuToggle = document.getElementById('menuToggle');
    const menuClose = document.getElementById('menuClose');
    const sideMenu = document.getElementById('sideMenu');
    const menuOverlay = document.getElementById('menuOverlay');

    function setMenuOpen(isOpen) {
        document.body.classList.toggle('menu-open', isOpen);
        menuToggle?.setAttribute('aria-expanded', String(isOpen));
        menuToggle?.setAttribute('aria-label', isOpen ? 'Cerrar menú' : 'Abrir menú');
        sideMenu?.setAttribute('aria-hidden', String(!isOpen));
        if (sideMenu) sideMenu.inert = !isOpen;
        if (isOpen) menuClose?.focus();
        else menuToggle?.focus();
    }

    menuToggle?.addEventListener('click', () => {
        setMenuOpen(menuToggle.getAttribute('aria-expanded') !== 'true');
    });
    menuClose?.addEventListener('click', () => setMenuOpen(false));
    menuOverlay?.addEventListener('click', () => setMenuOpen(false));
    sideMenu?.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => setMenuOpen(false));
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && document.body.classList.contains('menu-open')) {
            setMenuOpen(false);
        }
    });

});

// Manejo de teclas
document.addEventListener('keydown', (e) => {
    // ESC para cerrar modales
    if (e.key === 'Escape') {
        const modals = document.querySelectorAll('.modal.show');
        modals.forEach(modal => {
            const bsModal = bootstrap.Modal.getInstance(modal) || bootstrap.Modal.getOrCreateInstance(modal);
            if (bsModal && typeof bsModal.hide === 'function') {
                bsModal.hide();
            }
        });
    }

    // Enter en formularios
    if (e.key === 'Enter' && e.ctrlKey) {
        const form = document.querySelector('form:focus-within');
        if (form) {
            form.dispatchEvent(new Event('submit'));
        }
    }
});

console.log('STOCKFLOW - Sistema de Gestión Cargado Correctamente');
window.addEventListener('pageshow', cleanupModalResidues);
window.addEventListener('load', cleanupModalResidues);

document.addEventListener('hidden.bs.modal', () => {
    setTimeout(cleanupModalResidues, 100);
});

window.addEventListener('load', () => {

    console.log('LIMPIEZA FORZADA');

    document.body.classList.remove('modal-open');

    document.querySelectorAll('.modal-backdrop')
        .forEach(el => el.remove());

    document.body.style.overflow = '';
    document.body.style.paddingRight = '';

    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    });

});

const modalBackdrop = document.querySelector('.modal-backdrop');
if (modalBackdrop) {
    modalBackdrop.style.pointerEvents = 'none';
}