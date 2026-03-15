// static/js/main.js - 主JavaScript文件

// 全局配置
const API_BASE_URL = window.location.origin;
const DEFAULT_AVATAR = '/default_avatar.png';
const DEFAULT_COVER = '/static/images/default-cover.jpg';

// DOM加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 初始化组件
    initNavigation();
    initModals();
    initForms();
    initTooltips();
    initNotifications();
    
    // 检查用户登录状态
    checkAuthStatus();
    
    // 页面特定初始化
    if (typeof initPage !== 'undefined') {
        initPage();
    }
});

// 导航栏功能
function initNavigation() {
    const navToggle = document.getElementById('navToggle');
    const navMenu = document.getElementById('navMenu');
    
    if (navToggle && navMenu) {
        navToggle.addEventListener('click', () => {
            navMenu.classList.toggle('active');
            navToggle.innerHTML = navMenu.classList.contains('active') 
                ? '<i class="fas fa-times"></i>' 
                : '<i class="fas fa-bars"></i>';
        });
    }
    
    // 用户下拉菜单
    const userMenuBtn = document.getElementById('userMenuBtn');
    const userDropdown = document.getElementById('userDropdown');
    
    if (userMenuBtn && userDropdown) {
        userMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdown.classList.toggle('show');
        });
        
        // 点击其他地方关闭下拉菜单
        document.addEventListener('click', () => {
            userDropdown.classList.remove('show');
        });
    }
}

// 模态框功能
function initModals() {
    // 打开模态框
    document.querySelectorAll('[data-modal]').forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            const modalId = button.getAttribute('data-modal');
            const modal = document.getElementById(modalId);
            if (modal) {
                modal.classList.add('show');
                document.body.style.overflow = 'hidden';
            }
        });
    });
    
    // 关闭模态框
    document.querySelectorAll('.modal-close, .modal-cancel').forEach(button => {
        button.addEventListener('click', () => {
            const modal = button.closest('.modal');
            if (modal) {
                modal.classList.remove('show');
                document.body.style.overflow = '';
            }
        });
    });
    
    // 点击模态框背景关闭
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('show');
                document.body.style.overflow = '';
            }
        });
    });
}

// 表单处理
function initForms() {
    // 实时验证
    document.querySelectorAll('.form-control').forEach(input => {
        input.addEventListener('blur', validateField);
        input.addEventListener('input', clearFieldError);
    });
    
    // 表单提交
    document.querySelectorAll('form[data-ajax]').forEach(form => {
        form.addEventListener('submit', handleAjaxSubmit);
    });
}

// 字段验证
function validateField(e) {
    const field = e.target;
    const value = field.value.trim();
    const fieldName = field.getAttribute('name');
    const feedback = field.nextElementSibling;
    
    // 清除之前的错误状态
    field.classList.remove('is-invalid');
    
    if (feedback && feedback.classList.contains('invalid-feedback')) {
        feedback.textContent = '';
    }
    
    // 必填字段验证
    if (field.hasAttribute('required') && !value) {
        showFieldError(field, '此字段为必填项');
        return false;
    }
    
    // 邮箱验证
    if (fieldName === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            showFieldError(field, '请输入有效的邮箱地址');
            return false;
        }
    }
    
    // 密码强度验证
    if (fieldName === 'password' && value.length < 6) {
        showFieldError(field, '密码至少需要6个字符');
        return false;
    }
    
    // 确认密码验证
    if (fieldName === 'confirm_password' && value) {
        const password = field.form.querySelector('[name="password"]').value;
        if (value !== password) {
            showFieldError(field, '两次输入的密码不一致');
            return false;
        }
    }
    
    return true;
}

function showFieldError(field, message) {
    field.classList.add('is-invalid');
    
    let feedback = field.nextElementSibling;
    if (!feedback || !feedback.classList.contains('invalid-feedback')) {
        feedback = document.createElement('div');
        feedback.className = 'invalid-feedback';
        field.parentNode.insertBefore(feedback, field.nextSibling);
    }
    
    feedback.textContent = message;
}

function clearFieldError(e) {
    const field = e.target;
    field.classList.remove('is-invalid');
    
    const feedback = field.nextElementSibling;
    if (feedback && feedback.classList.contains('invalid-feedback')) {
        feedback.textContent = '';
    }
}

// AJAX表单提交
async function handleAjaxSubmit(e) {
    e.preventDefault();
    
    const form = e.target;
    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.innerHTML;
    const method = form.getAttribute('method') || 'POST';
    const url = form.getAttribute('action') || window.location.href;
    
    // 验证所有字段
    let isValid = true;
    form.querySelectorAll('.form-control').forEach(field => {
        if (!validateField({ target: field })) {
            isValid = false;
        }
    });
    
    if (!isValid) {
        showNotification('请检查表单中的错误', 'error');
        return;
    }
    
    // 准备表单数据
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    
    // 显示加载状态
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> 处理中...';
    
    try {
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // 成功处理
            if (result.redirect) {
                window.location.href = result.redirect;
            } else if (result.message) {
                showNotification(result.message, 'success');
                form.reset();
            }
            
            // 如果有回调函数
            if (form.dataset.callback && typeof window[form.dataset.callback] === 'function') {
                window[form.dataset.callback](result);
            }
        } else {
            // 错误处理
            showNotification(result.error || '请求失败', 'error');
        }
    } catch (error) {
        console.error('表单提交错误:', error);
        showNotification('网络错误，请稍后重试', 'error');
    } finally {
        // 恢复按钮状态
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
    }
}

// 工具提示
function initTooltips() {
    const tooltips = document.querySelectorAll('[data-tooltip]');
    
    tooltips.forEach(element => {
        element.addEventListener('mouseenter', showTooltip);
        element.addEventListener('mouseleave', hideTooltip);
    });
}

function showTooltip(e) {
    const element = e.target;
    const tooltipText = element.getAttribute('data-tooltip');
    
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.textContent = tooltipText;
    
    document.body.appendChild(tooltip);
    
    const rect = element.getBoundingClientRect();
    tooltip.style.position = 'fixed';
    tooltip.style.top = (rect.top - tooltip.offsetHeight - 10) + 'px';
    tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
    
    element._tooltip = tooltip;
}

function hideTooltip(e) {
    const element = e.target;
    if (element._tooltip) {
        element._tooltip.remove();
        delete element._tooltip;
    }
}

// 通知系统
function initNotifications() {
    // 创建通知容器
    const container = document.createElement('div');
    container.id = 'notification-container';
    document.body.appendChild(container);
}

function showNotification(message, type = 'info', duration = 5000) {
    const container = document.getElementById('notification-container');
    if (!container) return;
    
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            <i class="fas fa-${getNotificationIcon(type)}"></i>
            <span>${message}</span>
        </div>
        <button class="notification-close"><i class="fas fa-times"></i></button>
    `;
    
    container.appendChild(notification);
    
    // 添加显示动画
    setTimeout(() => notification.classList.add('show'), 10);
    
    // 关闭按钮
    notification.querySelector('.notification-close').addEventListener('click', () => {
        closeNotification(notification);
    });
    
    // 自动关闭
    if (duration > 0) {
        setTimeout(() => closeNotification(notification), duration);
    }
    
    return notification;
}

function closeNotification(notification) {
    notification.classList.remove('show');
    setTimeout(() => {
        if (notification.parentNode) {
            notification.parentNode.removeChild(notification);
        }
    }, 300);
}

function getNotificationIcon(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    return icons[type] || 'info-circle';
}

// 用户认证状态检查
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/me');
        if (response.ok) {
            const data = await response.json();
            window.user = data.user;
            updateUIForLoggedInUser(data.user);
        }
    } catch (error) {
        // 静默处理错误
    }
}

function updateUIForLoggedInUser(user) {
    // 更新用户相关UI
    const authElements = document.querySelectorAll('[data-auth]');
    authElements.forEach(element => {
        const authType = element.getAttribute('data-auth');
        if (authType === 'required') {
            element.style.display = 'block';
        } else if (authType === 'guest') {
            element.style.display = 'none';
        }
    });
    
    // 更新用户信息
    const userAvatar = document.querySelector('.user-avatar img');
    const userName = document.querySelector('.user-name');
    
    if (userAvatar && user.avatar) {
        // 构建完整的头像URL
        if (user.avatar.startsWith('http') || user.avatar.startsWith('/')) {
            userAvatar.src = user.avatar;
        } else {
            userAvatar.src = `/uploads/avatars/${user.avatar}`;
        }
        // 添加错误处理
        userAvatar.onerror = function() {
            this.src = '/default_avatar.png';
        };
    }
    
    if (userName) {
        userName.textContent = user.username;
    }
}

// 文件上传处理
function handleFileUpload(input, previewId, callback) {
    const file = input.files[0];
    if (!file) return;
    
    // 文件类型验证
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'video/mp4'];
    if (!allowedTypes.includes(file.type)) {
        showNotification('不支持的文件类型', 'error');
        input.value = '';
        return;
    }
    
    // 文件大小验证 (10MB)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
        showNotification('文件大小不能超过10MB', 'error');
        input.value = '';
        return;
    }
    
    // 预览
    if (previewId) {
        const preview = document.getElementById(previewId);
        if (preview) {
            if (file.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    preview.src = e.target.result;
                    preview.style.display = 'block';
                };
                reader.readAsDataURL(file);
            } else if (file.type.startsWith('video/')) {
                preview.src = URL.createObjectURL(file);
                preview.style.display = 'block';
            }
        }
    }
    
    if (callback && typeof callback === 'function') {
        callback(file);
    }
}

// API请求封装
async function apiRequest(endpoint, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'include'
    };
    
    const mergedOptions = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, mergedOptions);
        
        if (response.status === 401) {
            // 未授权，跳转到登录页
            window.location.href = '/login';
            return null;
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || '请求失败');
        }
        
        return data;
    } catch (error) {
        console.error('API请求错误:', error);
        showNotification(error.message, 'error');
        throw error;
    }
}

// 项目相关API
const ProjectAPI = {
    // 获取项目列表
    getProjects: async (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return await apiRequest(`/api/projects?${query}`);
    },
    
    // 获取单个项目
    getProject: async (id) => {
        return await apiRequest(`/api/projects/${id}`);
    },
    
    // 创建项目
    createProject: async (data) => {
        return await apiRequest('/api/projects', {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    
    // 更新项目
    updateProject: async (id, data) => {
        return await apiRequest(`/api/projects/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },
    
    // 删除项目
    deleteProject: async (id) => {
        return await apiRequest(`/api/projects/${id}`, {
            method: 'DELETE'
        });
    },
    
    // 上传封面
    uploadCover: async (projectId, file) => {
        const formData = new FormData();
        formData.append('cover', file);
        
        return await apiRequest(`/api/projects/${projectId}/cover`, {
            method: 'POST',
            headers: {},
            body: formData
        });
    },
    
    // 获取项目统计
    getStats: async () => {
        return await apiRequest('/api/projects/stats');
    },
    
    // 获取项目分析
    getAnalytics: async (projectId) => {
        return await apiRequest(`/api/projects/${projectId}/analytics`);
    },
    
    // 批量更新项目状态
    batchUpdateStatus: async (projectIds, status) => {
        return await apiRequest('/api/projects/batch/update-status', {
            method: 'POST',
            body: JSON.stringify({ project_ids: projectIds, status: status })
        });
    },
    
    // 高级搜索项目
    searchProjects: async (params = {}) => {
        const query = new URLSearchParams(params).toString();
        return await apiRequest(`/api/projects/search?${query}`);
    }
};

// 分集相关API
const EpisodeAPI = {
    // 获取分集列表
    getEpisodes: async (projectId) => {
        return await apiRequest(`/api/projects/${projectId}/episodes`);
    },
    
    // 创建分集
    createEpisode: async (projectId, data) => {
        return await apiRequest(`/api/projects/${projectId}/episodes`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    
    // 更新分集
    updateEpisode: async (episodeId, data) => {
        return await apiRequest(`/api/episodes/${episodeId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },
    
    // 删除分集
    deleteEpisode: async (episodeId) => {
        return await apiRequest(`/api/episodes/${episodeId}`, {
            method: 'DELETE'
        });
    },
    
    // 上传视频
    uploadVideo: async (episodeId, file) => {
        const formData = new FormData();
        formData.append('video', file);
        
        return await apiRequest(`/api/episodes/${episodeId}/video`, {
            method: 'POST',
            headers: {},
            body: formData
        });
    }
};

// 角色相关API
const CharacterAPI = {
    // 获取角色列表
    getCharacters: async (projectId) => {
        return await apiRequest(`/api/projects/${projectId}/characters`);
    },
    
    // 创建角色
    createCharacter: async (projectId, data) => {
        return await apiRequest(`/api/projects/${projectId}/characters`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },
    
    // 更新角色
    updateCharacter: async (characterId, data) => {
        return await apiRequest(`/api/characters/${characterId}`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },
    
    // 删除角色
    deleteCharacter: async (characterId) => {
        return await apiRequest(`/api/characters/${characterId}`, {
            method: 'DELETE'
        });
    }
};

// 导出到全局作用域
window.ProjectAPI = ProjectAPI;
window.EpisodeAPI = EpisodeAPI;
window.CharacterAPI = CharacterAPI;
window.showNotification = showNotification;
window.handleFileUpload = handleFileUpload;