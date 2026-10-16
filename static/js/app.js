    function app() {
      return {
        // i18n
        lang: 'en',
        t(key, params = {}) {
          let text = (window.I18N && window.I18N[this.lang] && window.I18N[this.lang][key]) 
                  || (window.I18N && window.I18N['uk'] && window.I18N['uk'][key]) 
                  || key;
          for (const [k, v] of Object.entries(params)) {
            text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
          }
          return text;
        },
        appT(key) {
          return this.t(key);
        },
        setLang(newLang) {
          this.lang = newLang;
          this.settingsForm.language = newLang;
          document.documentElement.lang = newLang;
        },

        // Auth state
        token: localStorage.getItem('torr2jelly_token') || '',
        currentUser: null,
        isLoggedIn: false,
        authModalOpen: false,
        authMode: 'login', // 'login' or 'setup'
        authForm: { username: '', password: '', confirmPassword: '' },
        authError: '',
        authLoading: false,

        // Password change modal
        changePwModalOpen: false,
        changePwForm: { currentPassword: '', newPassword: '', confirmPassword: '' },
        changePwError: '',
        changePwLoading: false,

        // Admin Reset password
        resetPwModalOpen: false,
        resetPwTargetUser: null,
        resetPwForm: { newPassword: '' },

        // File Manager state
        fileManagerModalOpen: false,
        fileManagerLoading: false,
        currentFileManagerTorrent: null,
        fileManagerData: { root_dir: '', folders: [], files: [] },
        selectedFiles: [],
        targetMoveFolder: '',
        organizingSeasons: false,

        // Toast Notifications state
        toasts: [],
        notify(message, type = 'success') {
          const id = Date.now() + Math.random();
          this.toasts.push({ id, message, type });
          setTimeout(() => {
            this.removeToast(id);
          }, 4500);
        },
        removeToast(id) {
          this.toasts = this.toasts.filter(t => t.id !== id);
        },

        // Rename Torrent Modal state
        renameModalOpen: false,
        renameTargetTorrent: null,
        renameForm: { title: '', rename_folder: true, category: 'movie' },
        renamingLoading: false,

        openRenameModal(torrent) {
          if (!torrent) return;
          this.renameTargetTorrent = torrent;
          this.renameForm = {
            title: torrent.clean_title || torrent.title || '',
            rename_folder: true,
            category: torrent.category || 'movie'
          };
          this.renameModalOpen = true;
        },

        async submitRenameTorrent() {
          if (!this.renameTargetTorrent || !this.renameForm.title.trim()) return;
          this.renamingLoading = true;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.renameTargetTorrent.hash + '/rename', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                title: this.renameForm.title.trim(),
                rename_folder: this.renameForm.rename_folder,
                category: this.renameForm.category
              })
            });
            const data = await res.json();
            if (res.ok) {
              const updatedTitle = data.clean_title || this.renameForm.title.trim();
              this.notify(this.t('torrent_renamed_success', { title: updatedTitle }), 'success');
              this.renameModalOpen = false;
              await this.loadTorrents();
              if (this.currentFileManagerTorrent && this.currentFileManagerTorrent.hash === this.renameTargetTorrent.hash) {
                this.currentFileManagerTorrent.clean_title = updatedTitle;
                this.currentFileManagerTorrent.title = data.title || updatedTitle;
                await this.loadFilesStructure();
              }
            } else {
              this.notify(data.detail || 'Failed to rename', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.renamingLoading = false;
          }
        },

        // Poster Modal state
        posterModalOpen: false,
        currentPosterTorrent: null,
        posterInputUrl: '',
        posterLoading: false,

        // User dropdown & users list
        userMenuOpen: false,
        usersList: [],
        newUserForm: { username: '', password: '', role: 'user' },
        addingUser: false,

        // Application state
        activeTab: 'search',
        status: {},
        torrents: [],
        searchResults: [],
        filterStatus: 'all',
        sortBy: 'priority',
        searchQuery: '',
        searchQueryTitle: '',
        selectedTorrentCategory: 'all',
        searchDefaultCategory: 'auto',
        searching: false,
        addingGuid: null,
        syncing: false,
        submitting: false,
        savingSettings: false,
        testingService: null,
        testingAllServices: false,
        serviceTestStatus: {},
        settingsForm: {
          prowlarr_url: '',
          prowlarr_api_key: '',
          jellyfin_url: '',
          jellyfin_api_key: '',
          torrserver_url: '',
          jellyfin_stream_torr_url: '',
          media_dir: '/media',
          categories: [
            { id: 'movie', name: 'Movies', type: 'movie', path: 'movies' },
            { id: 'show', name: 'Shows', type: 'show', path: 'shows' }
          ],
          auto_sync: true,
          sync_interval: 30,
          language: 'en',
          only_gold_torrents: false
        },

        get availableCategories() {
          if (this.settingsForm.categories && this.settingsForm.categories.length > 0) {
            return this.settingsForm.categories;
          }
          if (this.status && this.status.categories && this.status.categories.length > 0) {
            return this.status.categories;
          }
          return [
            { id: 'movie', name: this.t('badge_movie'), type: 'movie', path: 'movies' },
            { id: 'show', name: this.t('badge_show'), type: 'show', path: 'shows' }
          ];
        },

        resolveCategoryPath(catPath) {
          if (!catPath) return this.settingsForm.media_dir || '/media';
          if (catPath.startsWith('/')) return catPath;
          const base = (this.settingsForm.media_dir || '/media').replace(/\/+$/, '');
          return base + '/' + catPath.replace(/^\/+/, '');
        },

        addCategory() {
          if (!this.settingsForm.categories) this.settingsForm.categories = [];
          const num = this.settingsForm.categories.length + 1;
          this.settingsForm.categories.push({
            id: 'category_' + num,
            name: '',
            type: 'movie',
            path: ''
          });
        },

        removeCategory(index) {
          if (!this.settingsForm.categories) return;
          const cat = this.settingsForm.categories[index];
          if (this.settingsForm.categories.length <= 1) {
            this.notify(this.t('cannot_delete_default_cat'), 'error');
            return;
          }
          if (confirm(this.t('delete_category_confirm', { name: cat.name || cat.id }))) {
            this.settingsForm.categories.splice(index, 1);
          }
        },

        getCategoryLabel(catId) {
          if (!catId) return '';
          const cats = this.availableCategories;
          const found = cats.find(c => c.id === catId);
          if (found && found.name) return found.name;
          if (catId === 'movie') return this.t('badge_movie');
          if (catId === 'show') return this.t('badge_show');
          return catId;
        },

        getCategoryBadgeClass(catId) {
          if (catId === 'movie') return 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:border-cyan-400';
          if (catId === 'show') return 'bg-brand-500/20 text-brand-400 border border-brand-500/30 hover:border-brand-400';
          return 'bg-purple-500/20 text-purple-300 border border-purple-500/30 hover:border-purple-300';
        },

        async changeTorrentCategory(torrent, newCat) {
          if (!torrent || !newCat || torrent.category === newCat) return;
          const oldCat = torrent.category;
          torrent.category = newCat;
          try {
            const res = await this.apiFetch('/api/torrents/' + torrent.hash + '/category', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ category: newCat })
            });
            const data = await res.json();
            if (res.ok) {
              this.notify(this.t('category_changed_success', { category: this.getCategoryLabel(newCat) }), 'success');
              await this.loadTorrents();
            } else {
              torrent.category = oldCat;
              this.notify(data.detail || 'Failed to change category', 'error');
            }
          } catch (e) {
            torrent.category = oldCat;
            this.notify('Error: ' + e, 'error');
          }
        },
        form: {
          link: '',
          title: '',
          category: 'auto',
          sync_now: true
        },

        get isAdmin() {
          return this.currentUser && this.currentUser.role === 'admin';
        },

        async init() {
          document.documentElement.lang = this.lang;
          await this.checkAuthStatus();
          setInterval(() => {
            if (this.isLoggedIn) {
              this.loadStatus();
            }
          }, 10000);
          setInterval(() => {
            if (this.isLoggedIn) {
              this.loadTorrents();
            }
          }, 15000);
          setInterval(() => {
            if (this.isLoggedIn && this.torrents && this.torrents.some(t => this.isTorrentActive(t))) {
              this.loadTorrents();
            }
          }, 3000);
        },

        // Core API fetch wrapper attaching Bearer token and handling 401
        async apiFetch(url, options = {}) {
          options.headers = options.headers || {};
          if (this.token) {
            options.headers['Authorization'] = `Bearer ${this.token}`;
          }
          try {
            const res = await fetch(url, options);
            if (res.status === 401 && this.isLoggedIn) {
              this.logout(this.t('session_expired'));
              throw new Error('Unauthorized');
            }
            return res;
          } catch (e) {
            throw e;
          }
        },

        async checkAuthStatus() {
          try {
            const res = await fetch('/api/auth/setup-status');
            const data = await res.json();
            if (data.language) {
              this.lang = data.language;
              this.settingsForm.language = data.language;
              document.documentElement.lang = this.lang;
            }
            if (data.setup_required) {
              this.authMode = 'setup';
              this.authModalOpen = true;
              this.isLoggedIn = false;
              return;
            }

            if (this.token) {
              const meRes = await this.apiFetch('/api/auth/me');
              if (meRes.ok) {
                this.currentUser = await meRes.json();
                this.isLoggedIn = true;
                this.authModalOpen = false;
                await this.onLoggedIn();
                return;
              }
            }
          } catch (e) {
            console.error('Error during auth check:', e);
          }

          // Fallback: show login modal
          this.authMode = 'login';
          this.authModalOpen = true;
          this.isLoggedIn = false;
        },

        async submitAuth() {
          this.authError = '';
          this.authLoading = true;
          try {
            if (this.authMode === 'setup') {
              if (this.authForm.password !== this.authForm.confirmPassword) {
                this.authError = this.lang === 'uk' ? 'Паролі не співпадають' : 'Passwords do not match';
                return;
              }
              const res = await fetch('/api/auth/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  username: this.authForm.username.trim(),
                  password: this.authForm.password
                })
              });
              const data = await res.json();
              if (!res.ok) {
                this.authError = data.detail || (this.lang === 'uk' ? 'Помилка налаштування' : 'Setup error');
                return;
              }
              this.token = data.token;
              localStorage.setItem('torr2jelly_token', this.token);
              this.currentUser = data.user;
              this.isLoggedIn = true;
              this.authModalOpen = false;
              await this.onLoggedIn();
            } else {
              const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  username: this.authForm.username.trim(),
                  password: this.authForm.password
                })
              });
              const data = await res.json();
              if (!res.ok) {
                this.authError = data.detail || (this.lang === 'uk' ? 'Невірне ім\'я або пароль' : 'Invalid username or password');
                return;
              }
              this.token = data.token;
              localStorage.setItem('torr2jelly_token', this.token);
              this.currentUser = data.user;
              this.isLoggedIn = true;
              this.authModalOpen = false;
              await this.onLoggedIn();
            }
          } catch (e) {
            this.authError = (this.lang === 'uk' ? 'Помилка мережі: ' : 'Network error: ') + e;
          } finally {
            this.authLoading = false;
          }
        },

        async onLoggedIn() {
          await this.loadStatus();
          await this.loadTorrents();
          if (this.isAdmin) {
            await this.loadSettings();
            await this.loadUsersList();
          } else {
            if (this.activeTab === 'settings') {
              this.activeTab = 'search';
            }
          }
        },

        logout(errorMsg = '') {
          this.token = '';
          localStorage.removeItem('torr2jelly_token');
          this.currentUser = null;
          this.isLoggedIn = false;
          this.userMenuOpen = false;
          this.authForm = { username: '', password: '', confirmPassword: '' };
          this.authMode = 'login';
          this.authError = errorMsg;
          this.authModalOpen = true;
        },

        openChangePasswordModal() {
          this.changePwError = '';
          this.changePwForm = { currentPassword: '', newPassword: '', confirmPassword: '' };
          this.changePwModalOpen = true;
          this.userMenuOpen = false;
        },

        async submitChangePassword() {
          this.changePwError = '';
          if (this.changePwForm.newPassword !== this.changePwForm.confirmPassword) {
            this.changePwError = this.lang === 'uk' ? 'Нові паролі не співпадають' : 'New passwords do not match';
            return;
          }
          this.changePwLoading = true;
          try {
            const res = await this.apiFetch('/api/auth/change-password', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                current_password: this.changePwForm.currentPassword,
                new_password: this.changePwForm.newPassword
              })
            });
            if (res.ok) {
              this.notify(this.t('pw_changed_success'), 'success');
              this.changePwModalOpen = false;
            } else {
              const err = await res.json();
              this.changePwError = err.detail || 'Error';
            }
          } catch (e) {
            this.changePwError = 'Error: ' + e;
          } finally {
            this.changePwLoading = false;
          }
        },

        async loadUsersList() {
          if (!this.isAdmin) return;
          try {
            const res = await this.apiFetch('/api/users');
            if (res.ok) {
              this.usersList = await res.json();
            }
          } catch (e) {
            console.error('Failed to load users:', e);
          }
        },

        async createUser() {
          if (!this.isAdmin) return;
          this.addingUser = true;
          try {
            const res = await this.apiFetch('/api/users', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.newUserForm)
            });
            if (res.ok) {
              this.newUserForm = { username: '', password: '', role: 'user' };
              await this.loadUsersList();
              this.notify(this.t('user_created_success'), 'success');
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.addingUser = false;
          }
        },

        async deleteUser(username) {
          if (!confirm(this.t('confirm_delete_user', { user: username }))) return;
          try {
            const res = await this.apiFetch(`/api/users/${encodeURIComponent(username)}`, {
              method: 'DELETE'
            });
            if (res.ok) {
              await this.loadUsersList();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        openResetPasswordModal(user) {
          this.resetPwTargetUser = user.username;
          this.resetPwForm.newPassword = '';
          this.resetPwModalOpen = true;
        },

        async submitAdminResetPassword() {
          if (!this.resetPwTargetUser || !this.resetPwForm.newPassword) return;
          try {
            const res = await this.apiFetch(`/api/users/${encodeURIComponent(this.resetPwTargetUser)}/reset-password`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ new_password: this.resetPwForm.newPassword })
            });
            if (res.ok) {
              this.notify(this.t('user_reset_success', { user: this.resetPwTargetUser }), 'success');
              this.resetPwModalOpen = false;
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        async loadSettings() {
          if (!this.isAdmin) return;
          try {
            const res = await this.apiFetch('/api/settings');
            if (res.ok) {
              const data = await res.json();
              this.settingsForm = Object.assign({}, this.settingsForm, data);
              if (data.language) {
                this.lang = data.language;
                document.documentElement.lang = this.lang;
              }
            }
          } catch (e) {
            console.error('Failed to load settings:', e);
          }
        },

        async saveSettingsForm() {
          if (!this.isAdmin) return;
          this.savingSettings = true;
          try {
            const res = await this.apiFetch('/api/settings', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(this.settingsForm)
            });
            if (res.ok) {
              this.notify(this.t('settings_saved'), 'success');
              await this.loadStatus();
            } else {
              this.notify(this.t('settings_save_error'), 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.savingSettings = false;
          }
        },

        async testService(serviceName) {
          if (!this.isAdmin) return;
          this.testingService = serviceName;
          this.serviceTestStatus[serviceName] = null;
          let url = '', apiKey = '';
          if (serviceName === 'prowlarr') {
            url = this.settingsForm.prowlarr_url;
            apiKey = this.settingsForm.prowlarr_api_key;
          } else if (serviceName === 'jellyfin') {
            url = this.settingsForm.jellyfin_url;
            apiKey = this.settingsForm.jellyfin_api_key;
          } else if (serviceName === 'torrserver') {
            url = this.settingsForm.torrserver_url;
          }

          try {
            const res = await this.apiFetch('/api/settings/test', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ service: serviceName, url: url, api_key: apiKey })
            });
            const data = await res.json();
            if (data.reachable) {
              this.serviceTestStatus[serviceName] = { ok: true, msg: this.t('conn_success') };
            } else {
              this.serviceTestStatus[serviceName] = { ok: false, msg: this.t('conn_failed') };
            }
          } catch (e) {
            this.serviceTestStatus[serviceName] = { ok: false, msg: this.t('req_error') + e };
          } finally {
            this.testingService = null;
          }
        },

        async testAllServices() {
          if (!this.isAdmin) return;
          this.testingAllServices = true;
          try {
            const [prowlRes, jellyRes, torrRes] = await Promise.all([
              this.apiFetch('/api/settings/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  service: 'prowlarr',
                  url: this.settingsForm.prowlarr_url,
                  api_key: this.settingsForm.prowlarr_api_key
                })
              }).then(r => r.json()).catch(() => ({ reachable: false })),

              this.apiFetch('/api/settings/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  service: 'jellyfin',
                  url: this.settingsForm.jellyfin_url,
                  api_key: this.settingsForm.jellyfin_api_key
                })
              }).then(r => r.json()).catch(() => ({ reachable: false })),

              this.apiFetch('/api/settings/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  service: 'torrserver',
                  url: this.settingsForm.torrserver_url
                })
              }).then(r => r.json()).catch(() => ({ reachable: false }))
            ]);

            this.status.prowlarr = { status: prowlRes.reachable ? 'online' : 'offline', url: this.settingsForm.prowlarr_url };
            this.status.jellyfin = { status: jellyRes.reachable ? 'online' : 'offline', url: this.settingsForm.jellyfin_url };
            this.status.torrserver = { status: torrRes.reachable ? 'online' : 'offline', url: this.settingsForm.torrserver_url };

            this.serviceTestStatus.prowlarr = { ok: prowlRes.reachable, msg: prowlRes.reachable ? this.t('conn_success') : this.t('conn_failed') };
            this.serviceTestStatus.jellyfin = { ok: jellyRes.reachable, msg: jellyRes.reachable ? this.t('conn_success') : this.t('conn_failed') };
            this.serviceTestStatus.torrserver = { ok: torrRes.reachable, msg: torrRes.reachable ? this.t('conn_success') : this.t('conn_failed') };

            const allOk = prowlRes.reachable && jellyRes.reachable && torrRes.reachable;
            if (allOk) {
              this.notify(this.t('all_services_ok'), 'success');
            } else {
              const failed = [];
              if (!torrRes.reachable) failed.push('TorrServer');
              if (!jellyRes.reachable) failed.push('Jellyfin');
              if (!prowlRes.reachable) failed.push('Prowlarr');
              this.notify(this.t('services_failed', { names: failed.join(', ') }), 'error');
            }
          } catch (e) {
            this.notify('Error testing services: ' + e, 'error');
          } finally {
            this.testingAllServices = false;
          }
        },

        async loadStatus() {
          try {
            const res = await this.apiFetch('/api/status');
            if (res && res.ok) {
              this.status = await res.json();
              if (this.status.language) {
                this.lang = this.status.language;
                this.settingsForm.language = this.status.language;
                document.documentElement.lang = this.lang;
              }
            }
          } catch (e) {
            console.error('Failed to load status:', e);
          }
        },

        async loadTorrents() {
          try {
            const res = await this.apiFetch('/api/torrents');
            if (res && res.ok) {
              this.torrents = await res.json();
            }
          } catch (e) {
            console.error('Failed to load torrents:', e);
          }
        },

        get filteredTorrents() {
          if (!this.searchQuery) return this.torrents;
          const q = this.searchQuery.toLowerCase();
          return this.torrents.filter(t =>
            t.clean_title.toLowerCase().includes(q) ||
            t.title.toLowerCase().includes(q)
          );
        },

        get displayedTorrentsCount() {
          return this.torrentCategorySections.reduce((sum, s) => sum + s.items.length, 0);
        },

        get activeCategoryPills() {
          const filtered = this.filteredTorrents;
          const cats = this.availableCategories || [];
          
          const counts = {};
          filtered.forEach(t => {
            const cat = t.category || 'movie';
            counts[cat] = (counts[cat] || 0) + 1;
          });

          const pills = [
            { id: 'all', name: this.t('category_filter_all'), count: filtered.length }
          ];

          const knownIds = new Set();
          cats.forEach(c => {
            knownIds.add(c.id);
            pills.push({
              id: c.id,
              name: c.name || c.id,
              count: counts[c.id] || 0
            });
          });

          let otherCount = 0;
          Object.keys(counts).forEach(k => {
            if (!knownIds.has(k)) {
              otherCount += counts[k];
            }
          });

          if (otherCount > 0) {
            pills.push({
              id: 'other',
              name: this.t('category_group_other'),
              count: otherCount
            });
          }

          return pills;
        },

        get torrentCategorySections() {
          const filtered = this.filteredTorrents;
          const cats = this.availableCategories || [];
          const selected = this.selectedTorrentCategory;

          const catMap = new Map();
          cats.forEach(c => catMap.set(c.id, []));
          const otherItems = [];

          filtered.forEach(t => {
            const cat = t.category || 'movie';
            if (catMap.has(cat)) {
              catMap.get(cat).push(t);
            } else {
              otherItems.push(t);
            }
          });

          const sections = [];
          cats.forEach(c => {
            if (selected !== 'all' && selected !== c.id) return;
            const items = catMap.get(c.id) || [];
            if (selected === c.id || items.length > 0) {
              sections.push({
                id: c.id,
                name: c.name || c.id,
                type: c.type || 'movie',
                path: c.path || '',
                items: items
              });
            }
          });

          if (otherItems.length > 0 && (selected === 'all' || selected === 'other')) {
            sections.push({
              id: 'other',
              name: this.t('category_group_other'),
              type: 'movie',
              path: '',
              items: otherItems
            });
          }

          return sections;
        },

        get goldCount() {
          return this.searchResults.filter(r => r.release_status === 'gold').length;
        },

        get filteredSearchResults() {
          let list = [...this.searchResults];
          if (this.filterStatus === 'gold') {
            list = list.filter(r => r.release_status === 'gold');
          }

          // Apply Sorting
          switch (this.sortBy) {
            case 'priority':
              list.sort((a, b) => (b.priority || 0) - (a.priority || 0) || (b.seeders || 0) - (a.seeders || 0));
              break;
            case 'seeders_desc':
              list.sort((a, b) => (b.seeders || 0) - (a.seeders || 0));
              break;
            case 'size_desc':
              list.sort((a, b) => (b.size || 0) - (a.size || 0));
              break;
            case 'size_asc':
              list.sort((a, b) => (a.size || 0) - (b.size || 0));
              break;
            case 'date_desc':
              list.sort((a, b) => new Date(b.publish_date || 0) - new Date(a.publish_date || 0));
              break;
            case 'title_asc':
              list.sort((a, b) => (a.title || '').localeCompare(b.title || ''));
              break;
          }
          return list;
        },

        async executeSearch() {
          if (!this.searchQueryTitle.trim()) return;
          this.searching = true;
          try {
            const res = await this.apiFetch(`/api/search?query=${encodeURIComponent(this.searchQueryTitle.trim())}`);
            if (res.ok) {
              this.searchResults = await res.json();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Search error', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.searching = false;
          }
        },

        async addFromSearch(item) {
          this.addingGuid = item.guid;
          try {
            const chosenCat = (item.category && item.category !== 'auto') ? item.category : (this.searchDefaultCategory !== 'auto' ? this.searchDefaultCategory : null);
            const payload = {
              link: item.link,
              title: item.title,
              category: chosenCat,
              sync_now: true
            };
            const res = await this.apiFetch('/api/torrents', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            });
            if (res.ok) {
              this.notify(this.t('torrent_added_success', { title: item.clean_title }), 'success');
              this.searchQueryTitle = '';
              this.searchResults = [];
              await this.loadTorrents();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Error adding torrent', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.addingGuid = null;
          }
        },

        guessTitle() {
          if (!this.form.link) return;
          const m = this.form.link.match(/dn=([^&]+)/);
          if (m) {
            try {
              let raw = decodeURIComponent(m[1].replace(/\+/g, ' '));
              raw = raw.replace(/\[.*?\]/g, '')
                       .replace(/\(\s*\d{4}.*?\)/g, '')
                       .replace(/\b(1080p|720p|2160p|4K|BDRip|WEB-DL|WEBRip|HEVC|x264|x265)\b/gi, '')
                       .replace(/[._]/g, ' ')
                       .trim();
              this.form.title = raw;
            } catch (e) {}
          }
        },

        async pasteClipboard() {
          try {
            const text = await navigator.clipboard.readText();
            this.form.link = text;
            this.guessTitle();
          } catch (e) {
            this.notify('Clipboard access denied', 'error');
          }
        },

        async submitTorrent() {
          if (!this.form.link) return;
          this.submitting = true;
          try {
            const payload = {
              link: this.form.link,
              title: this.form.title || null,
              category: this.form.category === 'auto' ? null : this.form.category,
              sync_now: this.form.sync_now
            };
            const res = await this.apiFetch('/api/torrents', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            });
            if (res.ok) {
              this.form.link = '';
              this.form.title = '';
              await this.loadTorrents();
              this.notify(this.t('torrent_added_success', { title: 'Media' }), 'success');
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Error adding torrent', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.submitting = false;
          }
        },

        async deleteTorrent(hash, title) {
          if (!confirm(this.t('confirm_delete_torrent', { title: title }))) return;
          try {
            const res = await this.apiFetch(`/api/torrents/${hash}?delete_strm=true`, { method: 'DELETE' });
            if (res.ok) {
              await this.loadTorrents();
            } else {
              this.notify('Error deleting torrent', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        async triggerSync() {
          this.syncing = true;
          try {
            const res = await this.apiFetch('/api/sync', { method: 'POST' });
            const data = await res.json();
            await this.loadTorrents();
            this.notify(this.t('sync_done', { torrents: data.stats.synced_torrents, files: data.stats.total_strm_files }), 'success');
          } catch (e) {
            this.notify('Sync error: ' + e, 'error');
          } finally {
            this.syncing = false;
          }
        },

        async refreshJellyfin() {
          try {
            const res = await this.apiFetch('/api/jellyfin/refresh', { method: 'POST' });
            if (res.ok) {
              this.notify(this.t('jellyfin_refresh_done'), 'success');
            } else {
              this.notify('Failed to refresh Jellyfin library', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        formatBytes(bytes) {
          if (!bytes || bytes === 0) return '0 B';
          const k = 1024;
          const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
          const i = Math.floor(Math.log(bytes) / Math.log(k));
          return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        formatSpeed(bytes) {
          if (!bytes || bytes <= 0) return '0 KB/s';
          return this.formatBytes(bytes) + (this.lang === 'uk' ? '/с' : '/s');
        },

        isTorrentActive(t) {
          if (!t) return false;
          if (t.download_speed > 0 || t.upload_speed > 0) return true;
          if (t.active_peers > 0) return true;
          if (t.stat === 1 || t.stat === 2 || t.stat === 3) return true;
          if (t.stat_string && t.stat_string.toLowerCase().includes('working')) return true;
          if (t.stat_string && t.stat_string.toLowerCase().includes('preload')) return true;
          return false;
        },

        formatDate(dateStr) {
          if (!dateStr) return '';
          try {
            const d = new Date(dateStr);
            const locale = this.lang === 'uk' ? 'uk-UA' : 'en-US';
            return d.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' });
          } catch (e) {
            return '';
          }
        },



        // File Structure Manager Methods
        openFileManager(torrent) {
          this.currentFileManagerTorrent = torrent;
          this.selectedFiles = [];
          this.targetMoveFolder = '';
          this.fileManagerModalOpen = true;
          this.loadFilesStructure();
        },

        async loadFilesStructure() {
          if (!this.currentFileManagerTorrent) return;
          this.fileManagerLoading = true;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentFileManagerTorrent.hash + '/files');
            if (res.ok) {
              this.fileManagerData = await res.json();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed to load files', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.fileManagerLoading = false;
          }
        },

        get fileGroups() {
          if (!this.fileManagerData || !this.fileManagerData.files) return [];
          const groups = {};
          groups[''] = [];
          if (this.fileManagerData.folders) {
            this.fileManagerData.folders.forEach(f => {
              groups[f] = [];
            });
          }
          this.fileManagerData.files.forEach(f => {
            const folder = f.folder || '';
            if (!groups[folder]) groups[folder] = [];
            groups[folder].push(f);
          });
          const result = [];
          if (groups[''].length > 0 || (Object.keys(groups).length === 1 && this.fileManagerData.files.length === 0)) {
            result.push({ folder: '', files: groups[''] });
          }
          Object.keys(groups).sort().forEach(k => {
            if (k !== '') {
              result.push({ folder: k, files: groups[k] });
            }
          });
          return result;
        },

        isGroupSelected(group) {
          if (!group.files.length) return false;
          return group.files.every(f => this.selectedFiles.includes(f.path));
        },

        toggleSelectGroup(group, isChecked) {
          const groupPaths = group.files.map(f => f.path);
          if (isChecked) {
            this.selectedFiles = Array.from(new Set([...this.selectedFiles, ...groupPaths]));
          } else {
            this.selectedFiles = this.selectedFiles.filter(p => !groupPaths.includes(p));
          }
        },

        async autoOrganizeSeasons() {
          if (!this.currentFileManagerTorrent) return;
          this.organizingSeasons = true;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentFileManagerTorrent.hash + '/files/organize', {
              method: 'POST'
            });
            const data = await res.json();
            if (res.ok) {
              if (data.organized > 0) {
                this.notify(this.t('auto_organize_done', { count: data.organized }), 'success');
              } else {
                this.notify(this.t('auto_organize_none'), 'info');
              }
              await this.loadFilesStructure();
              await this.loadTorrents();
            } else {
              this.notify(data.detail || 'Failed', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.organizingSeasons = false;
          }
        },

        async createFolder() {
          if (!this.currentFileManagerTorrent) return;
          const name = prompt(this.t('folder_name_prompt'), 'Season 01');
          if (!name || !name.trim()) return;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentFileManagerTorrent.hash + '/files/folder', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ folder_name: name.trim() })
            });
            if (res.ok) {
              await this.loadFilesStructure();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        async moveSelectedFiles() {
          if (!this.currentFileManagerTorrent || !this.selectedFiles.length) return;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentFileManagerTorrent.hash + '/files/move', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                files: this.selectedFiles,
                file_paths: this.selectedFiles,
                target_folder: this.targetMoveFolder
              })
            });
            if (res.ok) {
              this.selectedFiles = [];
              await this.loadFilesStructure();
              await this.loadTorrents();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed to move', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        async renameItem(itemPath, type) {
          if (!this.currentFileManagerTorrent) return;
          const currentName = itemPath.split('/').pop();
          const newName = prompt(this.t('rename_prompt'), currentName);
          if (!newName || !newName.trim() || newName.trim() === currentName) return;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentFileManagerTorrent.hash + '/files/rename', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                old_path: itemPath,
                new_path: newName.trim(),
                new_name: newName.trim()
              })
            });
            if (res.ok) {
              await this.loadFilesStructure();
              await this.loadTorrents();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed to rename', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        async deleteItem(itemPath) {
          if (!this.currentFileManagerTorrent) return;
          const name = itemPath.split('/').pop();
          if (!confirm(this.t('confirm_delete_item', { name: name }))) return;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentFileManagerTorrent.hash + '/files?path=' + encodeURIComponent(itemPath) + '&target_path=' + encodeURIComponent(itemPath), {
              method: 'DELETE'
            });
            if (res.ok) {
              this.selectedFiles = this.selectedFiles.filter(p => p !== itemPath && !p.startsWith(itemPath + '/'));
              await this.loadFilesStructure();
              await this.loadTorrents();
            } else {
              const err = await res.json();
              this.notify(err.detail || 'Failed to delete', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          }
        },

        // Poster Modal Methods
        openPosterModal(torrent) {
          this.currentPosterTorrent = torrent;
          this.posterInputUrl = torrent.poster || '';
          this.posterModalOpen = true;
        },

        async autoFindPoster() {
          if (!this.currentPosterTorrent) return;
          this.posterLoading = true;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentPosterTorrent.hash + '/poster', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ auto_fetch: true, auto_find: true })
            });
            const data = await res.json();
            if (res.ok && data.poster) {
              this.posterInputUrl = data.poster;
              this.currentPosterTorrent.poster = data.poster;
              const t = this.torrents.find(x => x.hash === this.currentPosterTorrent.hash);
              if (t) t.poster = data.poster;
              this.notify(this.t('poster_updated_success'), 'success');
            } else {
              this.notify(this.t('poster_not_found'), 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.posterLoading = false;
          }
        },

        async saveCustomPoster() {
          if (!this.currentPosterTorrent) return;
          this.posterLoading = true;
          try {
            const res = await this.apiFetch('/api/torrents/' + this.currentPosterTorrent.hash + '/poster', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ poster: this.posterInputUrl.trim() })
            });
            const data = await res.json();
            if (res.ok) {
              this.currentPosterTorrent.poster = data.poster;
              const t = this.torrents.find(x => x.hash === this.currentPosterTorrent.hash);
              if (t) t.poster = data.poster;
              this.notify(this.t('poster_updated_success'), 'success');
              this.posterModalOpen = false;
            } else {
              this.notify(data.detail || 'Failed', 'error');
            }
          } catch (e) {
            this.notify('Error: ' + e, 'error');
          } finally {
            this.posterLoading = false;
          }
        }
      }
    }
