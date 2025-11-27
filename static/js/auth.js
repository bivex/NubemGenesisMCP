// Authentication handler for Secrets UI
(function() {
    'use strict';

    // Check authentication on page load
    function checkAuth() {
        const token = localStorage.getItem('auth_token');
        const currentPath = window.location.pathname;

        // Skip auth check for login pages
        if (currentPath.includes('/secrets/login') || currentPath.includes('/auth/')) {
            return;
        }

        if (!token) {
            // No token, redirect to login
            console.log('No auth token found, redirecting to login');
            window.location.href = '/secrets/login';
            return;
        }

        // Token exists, verify it's valid by making a test request
        verifyToken(token);
    }

    // Verify token is still valid
    function verifyToken(token) {
        fetch('/api/v1/me', {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (response.status === 401) {
                // Token invalid/expired
                console.log('Token invalid, clearing and redirecting');
                clearAuth();
                window.location.href = '/secrets/login';
            } else if (response.ok) {
                return response.json();
            }
        })
        .then(user => {
            if (user) {
                displayUserInfo(user);
            }
        })
        .catch(error => {
            console.error('Error verifying token:', error);
        });
    }

    // Display user info in UI
    function displayUserInfo(user) {
        const userInfoElement = document.getElementById('userInfo');
        if (userInfoElement && user) {
            const picture = user.picture || '';
            const name = user.name || user.email;
            const email = user.email || '';

            userInfoElement.innerHTML = `
                <div class="flex items-center space-x-3">
                    ${picture ? `<img src="${picture}" alt="${name}" class="w-10 h-10 rounded-full">` : ''}
                    <div>
                        <div class="font-semibold text-gray-900">${name}</div>
                        <div class="text-sm text-gray-600">${email}</div>
                    </div>
                    <button onclick="logout()" class="ml-4 px-4 py-2 text-sm text-gray-700 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition">
                        Logout
                    </button>
                </div>
            `;
        }
    }

    // Clear authentication data
    function clearAuth() {
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_email');
        localStorage.removeItem('user_name');
        localStorage.removeItem('user_picture');
    }

    // Logout function (globally available)
    window.logout = function() {
        clearAuth();
        window.location.href = '/secrets/login';
    };

    // Add auth token to all htmx requests
    document.addEventListener('DOMContentLoaded', function() {
        // Configure htmx to include auth header
        document.body.addEventListener('htmx:configRequest', function(evt) {
            const token = localStorage.getItem('auth_token');
            if (token) {
                evt.detail.headers['Authorization'] = `Bearer ${token}`;
            }
        });

        // Handle htmx 401 responses
        document.body.addEventListener('htmx:responseError', function(evt) {
            if (evt.detail.xhr.status === 401) {
                clearAuth();
                window.location.href = '/secrets/login';
            }
        });

        // Check auth on load
        checkAuth();
    });

    // Helper function to make authenticated API calls
    window.apiCall = async function(url, options = {}) {
        const token = localStorage.getItem('auth_token');

        if (!token) {
            window.location.href = '/secrets/login';
            return null;
        }

        const defaultOptions = {
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        try {
            const response = await fetch(url, defaultOptions);

            if (response.status === 401) {
                clearAuth();
                window.location.href = '/secrets/login';
                return null;
            }

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Request failed');
            }

            // Handle 204 No Content
            if (response.status === 204) {
                return { success: true };
            }

            return await response.json();
        } catch (error) {
            console.error('API call error:', error);
            throw error;
        }
    };

    // Load secrets on dashboard
    window.loadSecrets = async function() {
        try {
            const secrets = await apiCall('/api/v1/secrets');
            if (secrets) {
                displaySecrets(secrets);
                updateStats(secrets);
            }
        } catch (error) {
            console.error('Error loading secrets:', error);
            showError('Failed to load secrets: ' + error.message);
        }
    };

    // Display secrets list
    function displaySecrets(secrets) {
        const listElement = document.getElementById('secretsList');
        if (!listElement) return;

        if (!secrets || secrets.length === 0) {
            listElement.innerHTML = `
                <div class="text-center py-12 text-gray-500">
                    <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"></path>
                    </svg>
                    <p class="text-lg font-medium">No secrets yet</p>
                    <p class="mt-2">Create your first secret to get started</p>
                </div>
            `;
            return;
        }

        const html = secrets.map(secret => `
            <div class="secret-card bg-white border border-gray-200 rounded-lg p-4">
                <div class="flex justify-between items-center">
                    <div class="flex-1">
                        <h3 class="font-semibold text-gray-900">${escapeHtml(secret.name)}</h3>
                        <p class="text-sm text-gray-500 mt-1">
                            <span class="inline-block w-32 h-2 bg-gray-300 rounded"></span>
                        </p>
                    </div>
                    <div class="flex space-x-2">
                        <button onclick="viewSecret('${escapeHtml(secret.name)}')"
                                class="px-3 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition">
                            View
                        </button>
                        <button onclick="editSecret('${escapeHtml(secret.name)}')"
                                class="px-3 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded-lg transition">
                            Edit
                        </button>
                        <button onclick="deleteSecret('${escapeHtml(secret.name)}')"
                                class="px-3 py-1 text-sm text-red-600 hover:bg-red-50 rounded-lg transition">
                            Delete
                        </button>
                    </div>
                </div>
            </div>
        `).join('');

        listElement.innerHTML = html;
    }

    // Update stats
    function updateStats(secrets) {
        document.getElementById('totalSecrets').textContent = secrets.length;
        document.getElementById('activeSecrets').textContent = secrets.length;
        document.getElementById('labeledSecrets').textContent = '0'; // TODO: count labeled secrets
    }

    // View secret
    window.viewSecret = async function(name) {
        try {
            const secret = await apiCall(`/api/v1/secrets/${encodeURIComponent(name)}`);
            if (secret) {
                showModal('View Secret', `
                    <div class="space-y-4">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Name</label>
                            <input type="text" value="${escapeHtml(secret.name)}" readonly
                                   class="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-2">Value</label>
                            <textarea readonly class="w-full px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 font-mono text-sm"
                                      rows="4">${escapeHtml(secret.value)}</textarea>
                        </div>
                    </div>
                `);
            }
        } catch (error) {
            showError('Failed to load secret: ' + error.message);
        }
    };

    // Create secret
    window.createSecret = async function() {
        const name = document.getElementById('newSecretName').value.trim();
        const value = document.getElementById('newSecretValue').value.trim();

        if (!name || !value) {
            showError('Name and value are required');
            return;
        }

        try {
            await apiCall('/api/v1/secrets', {
                method: 'POST',
                body: JSON.stringify({ name, value })
            });

            hideModal('createModal');
            document.getElementById('newSecretName').value = '';
            document.getElementById('newSecretValue').value = '';
            loadSecrets();
            showSuccess('Secret created successfully');
        } catch (error) {
            showError('Failed to create secret: ' + error.message);
        }
    };

    // Delete secret
    window.deleteSecret = async function(name) {
        if (!confirm(`Are you sure you want to delete "${name}"?`)) {
            return;
        }

        try {
            await apiCall(`/api/v1/secrets/${encodeURIComponent(name)}`, {
                method: 'DELETE'
            });
            loadSecrets();
            showSuccess('Secret deleted successfully');
        } catch (error) {
            showError('Failed to delete secret: ' + error.message);
        }
    };

    // Utility functions
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showModal(title, content) {
        // TODO: Implement modal system
        alert(title + '\n\n' + content);
    }

    function hideModal(id) {
        const modal = document.getElementById(id);
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    function showError(message) {
        // TODO: Implement toast notifications
        console.error(message);
        alert('Error: ' + message);
    }

    function showSuccess(message) {
        // TODO: Implement toast notifications
        console.log(message);
    }

})();
