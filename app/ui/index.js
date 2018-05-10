"use strict";
// api
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : new P(function (resolve) { resolve(result.value); }).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
const request = (method, url, init) => fetch(url, Object.assign({ method }, init))
    .then(response => response.json());
const fetchListeners = () => __awaiter(this, void 0, void 0, function* () {
    const response = yield request('GET', `https://lightspeed.parsecgaming.com/listeners/`)
        .then(Object.values);
    return response.map(listener => ({
        currentBranch: listener.config.branch_filter[0],
        name: listener.config.name,
        branches: Object.keys(listener.last_pushes)
    }));
});
const changeBranch = (name, branch) => request('PUT', `https://lightspeed.parsecgaming.com/listeners/`, {
    body: JSON.stringify({
        name,
        data: { branch_filter: [branch] }
    })
});
const retriggerListener = (name) => request('PUT', `https://lightspeed.parsecgaming.com/listeners/`, {
    body: JSON.stringify({
        name,
        retrigger: true
    })
});
// listener
function render(html) {
    const fragment = document
        .createRange()
        .createContextualFragment(`<div>${html}</div>`);
    return fragment.firstChild;
}
function renderListener(listener) {
    return render(`
    <li class="listener">
      <h2 class="listener-title">${listener.name}</h2>
      ${listener.branches.length ? `
        <select class="branches" data-listener="${listener.name}">
          ${listener.branches.map(branch => `<option${listener.currentBranch === branch ? ' selected' : ''}>${branch}</option>`)}
        </select>
      ` : `<span class="no-branches">${listener.name} has no registered branches.</span>`}
      ${listener.branches.length ? `<button class="deploy" data-listener="${listener.name}">Deploy</button>` : ''}
    </li>
  `);
}
// main
function init() {
    return __awaiter(this, void 0, void 0, function* () {
        const main = document.getElementById('main');
        const listenersList = document.getElementById('listeners');
        if (main && listenersList) {
            const listeners = yield fetchListeners();
            main.dataset.status = 'loading-repos';
            for (const listener of listeners) {
                listenersList.appendChild(renderListener(listener));
            }
            const branchSelects = document.querySelectorAll('.branches');
            Array.prototype.forEach.call(branchSelects, (select) => {
                select.addEventListener('change', () => select.dataset.listener && changeBranch(select.dataset.listener, select.value));
            });
            const deployButtons = document.querySelectorAll('.deploy');
            Array.prototype.forEach.call(deployButtons, (button) => {
                button.addEventListener('click', () => button.dataset.listener && retriggerListener(button.dataset.listener));
            });
        }
    });
}
init();
