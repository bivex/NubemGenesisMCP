/**
 * NubemSuperFClaude - Frontend Application
 * JavaScript utilities and htmx enhancements
 */

// Global application state
const App = {
    token: localStorage.getItem('auth_token') || null,
    user: null,

    // Initialize the application
    init() {
        console.log('NubemSuperFClaude initializing...');
        this.setupHttpInterceptors();
        this.setupHtmxConfig();
        this.setupNotifications();
        this.loadUserInfo();
    },

    // Setup HTTP request interceptors for authentication
    setupHttpInterceptors() {
        // Add Authorization header to all htmx requests
        document.body.addEventListener('htmx:configRequest', (event) => {
            if (this.token) {
                event.detail.headers['Authorization'] = `Bearer ${this.token}`;
            }
        });

        // Handle authentication errors
        document.body.addEventListener('htmx:responseError', (event) => {
            if (event.detail.xhr.status === 401) {
                this.showNotification('Session expired. Please login again.', 'error');
                this.logout();
            } else if (event.detail.xhr.status === 403) {
                this.showNotification('Access denied. Check your permissions.', 'error');
            } else if (event.detail.xhr.status === 429) {
                this.showNotification('Rate limit exceeded. Please try again later.', 'warning');
            } else {
                this.showNotification('An error occurred. Please try again.', 'error');
            }
        });

        // Show loading indicator
        document.body.addEventListener('htmx:beforeRequest', (event) => {
            this.showLoading();
        });

        document.body.addEventListener('htmx:afterRequest', (event) => {
            this.hideLoading();
        });
    },

    // Configure htmx settings
    setupHtmxConfig() {
        // Set default swap behavior
        htmx.config.defaultSwapStyle = 'innerHTML';
        htmx.config.defaultSwapDelay = 100;
        htmx.config.defaultSettleDelay = 100;
    },

    // Setup notification system
    setupNotifications() {
        this.notificationContainer = document.createElement('div');
        this.notificationContainer.id = 'notification-container';
        this.notificationContainer.className = 'fixed top-4 right-4 z-50 space-y-2';
        document.body.appendChild(this.notificationContainer);
    },

    // Show notification
    showNotification(message, type = 'info', duration = 3000) {
        const notification = document.createElement('div');
        notification.className = `notification-enter px-6 py-3 rounded-lg shadow-lg text-white ${this.getNotificationColor(type)}`;
        notification.textContent = message;

        this.notificationContainer.appendChild(notification);

        setTimeout(() => {
            notification.classList.add('notification-exit');
            setTimeout(() => notification.remove(), 300);
        }, duration);
    },

    // Get notification color based on type
    getNotificationColor(type) {
        const colors = {
            success: 'bg-green-500',
            error: 'bg-red-500',
            warning: 'bg-yellow-500',
            info: 'bg-blue-500'
        };
        return colors[type] || colors.info;
    },

    // Show loading indicator
    showLoading() {
        let loader = document.getElementById('global-loader');
        if (!loader) {
            loader = document.createElement('div');
            loader.id = 'global-loader';
            loader.className = 'fixed top-0 left-0 right-0 h-1 z-50';
            loader.innerHTML = '<div class="progress-bar"><div class="progress-bar-fill"></div></div>';
            document.body.appendChild(loader);
        }
        loader.style.display = 'block';
    },

    // Hide loading indicator
    hideLoading() {
        const loader = document.getElementById('global-loader');
        if (loader) {
            setTimeout(() => {
                loader.style.display = 'none';
            }, 200);
        }
    },

    // Load user information
    async loadUserInfo() {
        if (!this.token) return;

        try {
            const response = await fetch('/api/v1/me', {
                headers: {
                    'Authorization': `Bearer ${this.token}`
                }
            });

            if (response.ok) {
                this.user = await response.json();
                console.log('User loaded:', this.user.email);
            } else {
                this.logout();
            }
        } catch (error) {
            console.error('Error loading user:', error);
        }
    },

    // Set authentication token
    setToken(token) {
        this.token = token;
        localStorage.setItem('auth_token', token);
    },

    // Logout user
    logout() {
        this.token = null;
        this.user = null;
        localStorage.removeItem('auth_token');
        window.location.href = '/login';
    }
};

// Utility functions
const Utils = {
    // Copy text to clipboard
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            App.showNotification('Copied to clipboard!', 'success', 2000);
            return true;
        } catch (error) {
            App.showNotification('Failed to copy', 'error');
            return false;
        }
    },

    // Format date
    formatDate(dateString) {
        if (!dateString) return 'Unknown';
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    },

    // Format relative time
    formatRelativeTime(dateString) {
        if (!dateString) return 'Unknown';
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'Just now';
        if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;
        if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
        if (diffDays < 30) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

        return this.formatDate(dateString);
    },

    // Validate secret name
    validateSecretName(name) {
        const pattern = /^[a-zA-Z0-9_-]+$/;
        return pattern.test(name) && name.length > 0 && name.length <= 100;
    },

    // Validate JSON
    validateJSON(str) {
        try {
            JSON.parse(str);
            return true;
        } catch (e) {
            return false;
        }
    },

    // Truncate text
    truncate(text, maxLength = 50) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    },

    // Debounce function
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Throttle function
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
};

// Secret management functions
const Secrets = {
    // Create secret
    async create(name, value, labels = null) {
        try {
            const response = await fetch('/api/v1/secrets', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${App.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name, value, labels })
            });

            if (response.ok) {
                App.showNotification('Secret created successfully!', 'success');
                return await response.json();
            } else {
                const error = await response.json();
                App.showNotification(`Error: ${error.detail || 'Failed to create secret'}`, 'error');
                return null;
            }
        } catch (error) {
            App.showNotification('Network error', 'error');
            return null;
        }
    },

    // Get secret
    async get(name) {
        try {
            const response = await fetch(`/api/v1/secrets/${name}`, {
                headers: {
                    'Authorization': `Bearer ${App.token}`
                }
            });

            if (response.ok) {
                return await response.json();
            } else {
                App.showNotification('Secret not found', 'error');
                return null;
            }
        } catch (error) {
            App.showNotification('Network error', 'error');
            return null;
        }
    },

    // Update secret
    async update(name, value) {
        try {
            const response = await fetch(`/api/v1/secrets/${name}`, {
                method: 'PUT',
                headers: {
                    'Authorization': `Bearer ${App.token}`,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ value })
            });

            if (response.ok) {
                App.showNotification('Secret updated successfully!', 'success');
                return await response.json();
            } else {
                App.showNotification('Failed to update secret', 'error');
                return null;
            }
        } catch (error) {
            App.showNotification('Network error', 'error');
            return null;
        }
    },

    // Delete secret
    async delete(name) {
        if (!confirm(`Are you sure you want to delete "${name}"? This action cannot be undone.`)) {
            return false;
        }

        try {
            const response = await fetch(`/api/v1/secrets/${name}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${App.token}`
                }
            });

            if (response.ok) {
                App.showNotification('Secret deleted successfully!', 'success');
                return true;
            } else {
                App.showNotification('Failed to delete secret', 'error');
                return false;
            }
        } catch (error) {
            App.showNotification('Network error', 'error');
            return false;
        }
    },

    // List secrets
    async list() {
        try {
            const response = await fetch('/api/v1/secrets', {
                headers: {
                    'Authorization': `Bearer ${App.token}`
                }
            });

            if (response.ok) {
                return await response.json();
            } else {
                App.showNotification('Failed to load secrets', 'error');
                return [];
            }
        } catch (error) {
            App.showNotification('Network error', 'error');
            return [];
        }
    }
};

// Initialize application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => App.init());
} else {
    App.init();
}

// Export for global access
window.App = App;
window.Utils = Utils;
window.Secrets = Secrets;
window.copyToClipboard = Utils.copyToClipboard.bind(Utils);

console.log('NubemSuperFClaude v1.0.0 loaded');
