// api

const request = <Return> (method: 'GET' | 'PUT', url: string, init?: RequestInit) => fetch(url, {
  method,
  ...init
})
  .then(response => response.json() as Promise<Return>);

interface Listener {
  name: string;
  currentBranch: string;
  branches: string[];
}

const fetchListeners = async () => {
  const response = await request<any[]>('GET', `https://lightspeed.parsecgaming.com/listeners/`)
    .then(Object.values);

  return response.map<Listener>(listener => ({
    currentBranch: listener.config.branch_filter[0],
    name: listener.config.name,
    branches: Object.keys(listener.last_pushes)
  }));
};

const changeBranch = (name: string, branch: string) => request<any[]>('PUT', `https://lightspeed.parsecgaming.com/listeners/`, {
  body: JSON.stringify({
    name,
    data: { branch_filter: [branch] }
  })
});

const retriggerListener = (name: string) => request<any[]>('PUT', `https://lightspeed.parsecgaming.com/listeners/`, {
  body: JSON.stringify({
    name,
    retrigger: true
  })
});

// listener

function render (html: string) {
  const fragment = document
    .createRange()
    .createContextualFragment(`<div>${ html }</div>`);

  return fragment.firstChild as HTMLElement;
}

function renderListener (listener: Listener) {
  return render(`
    <li class="listener">
      <h2 class="listener-title">${ listener.name }</h2>
      ${ listener.branches.length ? `
        <select class="branches" data-listener="${ listener.name }">
          ${ listener.branches.map(branch => `<option${ listener.currentBranch === branch ? ' selected' : ''}>${ branch }</option>`) }
        </select>
      ` : `<span class="no-branches">${ listener.name } has no registered branches.</span>` }
      ${ listener.branches.length ? `<button class="deploy" data-listener="${ listener.name }">Deploy</button>` : '' }
    </li>
  `);
}

// main

async function init () {
  const main = document.getElementById('main');
  const listenersList = document.getElementById('listeners');

  if (main && listenersList) {

    const listeners = await fetchListeners();

    main.dataset.status = 'loading-repos';

    for (const listener of listeners) {
      listenersList.appendChild(
        renderListener(
          listener
        )
      );
    }

    const branchSelects = document.querySelectorAll('.branches');
    Array.prototype.forEach.call(branchSelects, (select: HTMLSelectElement) => {
      select.addEventListener('change', () => select.dataset.listener && changeBranch(select.dataset.listener, select.value));
    });

    const deployButtons = document.querySelectorAll('.deploy');
    Array.prototype.forEach.call(deployButtons, (button: HTMLButtonElement) => {
      button.addEventListener('click', () => button.dataset.listener && retriggerListener(button.dataset.listener));
    });
  }
}

init();
