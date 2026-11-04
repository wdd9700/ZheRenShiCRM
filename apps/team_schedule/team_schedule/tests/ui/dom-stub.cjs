'use strict';

class EventTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }

  async dispatchEvent(event) {
    event.target = event.target || this;
    for (const listener of this.listeners.get(event.type) || []) await listener(event);
    return event;
  }
}

class TextNode {
  constructor(text) {
    this.textContent = String(text);
    this.parentNode = null;
  }
}

function matches(element, selector) {
  if (!(element instanceof Element)) return false;
  let remaining = selector;
  if (remaining.endsWith(':checked')) {
    if (!element.checked) return false;
    remaining = remaining.slice(0, -8);
  }
  const attribute = remaining.match(/^([a-z0-9]+)\[name="([^"]+)"\]$/i);
  if (attribute) return element.tagName.toLowerCase() === attribute[1].toLowerCase() && element.name === attribute[2];
  const [tag, className] = remaining.split('.');
  if (tag && tag !== '*' && element.tagName.toLowerCase() !== tag.toLowerCase()) return false;
  if (className && !element.className.split(/\s+/).includes(className)) return false;
  return Boolean(tag || className);
}

function descendants(node) {
  const result = [];
  for (const child of node.children || []) {
    if (child instanceof Element) {
      result.push(child, ...descendants(child));
    }
  }
  return result;
}

class Element extends EventTarget {
  constructor(tagName, id = '') {
    super();
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.className = '';
    this.value = '';
    this.defaultValue = '';
    this.checked = false;
    this.defaultChecked = false;
    this.hidden = false;
    this.disabled = false;
    this.files = [];
    this.form = null;
    this.name = '';
    this.content = '';
    this._textContent = '';
    this.classList = {
      toggle: (name, force) => {
        const classes = new Set(this.className.split(/\s+/).filter(Boolean));
        if (force) classes.add(name);
        else classes.delete(name);
        this.className = [...classes].join(' ');
      }
    };
  }

  get textContent() {
    return this._textContent + this.children.map(child => child.textContent).join('');
  }

  set textContent(value) {
    this.children = [];
    this._textContent = String(value ?? '');
  }

  append(...nodes) {
    this._textContent = '';
    for (const node of nodes) {
      const child = typeof node === 'string' ? new TextNode(node) : node;
      child.parentNode = this;
      this.children.push(child);
    }
  }

  replaceChildren(...nodes) {
    for (const child of this.children) child.parentNode = null;
    this.children = [];
    this._textContent = '';
    this.append(...nodes);
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }

  querySelectorAll(selector) {
    return descendants(this).filter(element => matches(element, selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  scrollIntoView() {}

  click() {
    return this.dispatchEvent({type: 'click', target: this, preventDefault() { this.defaultPrevented = true; }});
  }

  reset() {
    if (this.tagName !== 'FORM' || !this.ownerDocument) return;
    for (const element of this.ownerDocument.elements.filter(candidate => candidate.form === this)) {
      if (element.tagName === 'SELECT') {
        element.value = element.defaultValue || (element.children[0] && element.children[0].value) || '';
      } else if (element.type === 'checkbox') {
        element.checked = element.defaultChecked;
      } else {
        element.value = element.defaultValue;
      }
    }
  }
}

class Document extends EventTarget {
  constructor() {
    super();
    this.body = new Element('body');
    this.body.ownerDocument = this;
    this.hidden = false;
    this.elements = [];
  }

  createElement(tagName) {
    const element = new Element(tagName);
    element.ownerDocument = this;
    return element;
  }

  createTextNode(text) {
    return new TextNode(text);
  }

  register(element) {
    element.ownerDocument = this;
    this.elements.push(element);
    this.body.append(element);
    return element;
  }

  getElementById(id) {
    return descendants(this.body).find(element => element.id === id) || null;
  }

  querySelectorAll(selector) {
    return descendants(this.body).filter(element => matches(element, selector));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

class Window extends EventTarget {
  constructor(fetchImpl) {
    super();
    this.fetch = fetchImpl;
    this.Intl = {supportedValuesOf: () => ['Asia/Shanghai', 'Asia/Kolkata', 'America/New_York']};
    this.confirmMessages = [];
    this.confirm = message => {
      this.confirmMessages.push(message);
      return true;
    };
    this.reloadCount = 0;
    this.location = {reload: () => { this.reloadCount += 1; }};
    let sequence = 0;
    this.crypto = {randomUUID: () => '00000000-0000-4000-8000-' + String(++sequence).padStart(12, '0')};
  }
}

function attributes(source) {
  return {
    id: (source.match(/\bid="([^"]*)"/) || [])[1] || '',
    className: (source.match(/\bclass="([^"]*)"/) || [])[1] || '',
    type: (source.match(/\btype="([^"]*)"/) || [])[1] || '',
    value: (source.match(/\bvalue="([^"]*)"/) || [])[1] || '',
    hidden: /\bhidden\b/.test(source),
    disabled: /\bdisabled\b/.test(source),
    checked: /\bchecked\b/.test(source)
  };
}

function createDom(html, fetchImpl) {
  const document = new Document();
  document.body.dataset.currentUser = 'owner@example.test';
  let currentForm = null;
  const tags = html.matchAll(/<(\/?)([a-z][a-z0-9]*)\b([^>]*)>/gi);
  for (const match of tags) {
    const [, closing, tag, source] = match;
    if (tag.toLowerCase() === 'form') {
      if (closing) currentForm = null;
      else {
        const values = attributes(source);
        const form = document.register(new Element('form', values.id));
        form.form = null;
        currentForm = form;
      }
      continue;
    }
    if (closing) continue;
    const values = attributes(source);
    if (!values.id) continue;
    const element = document.register(new Element(tag, values.id));
    element.className = values.className;
    element.type = values.type;
    element.value = values.value;
    element.defaultValue = values.value;
    element.hidden = values.hidden;
    element.disabled = values.disabled;
    element.checked = values.checked;
    element.defaultChecked = values.checked;
    element.form = currentForm;
  }
  const meta = document.register(new Element('meta'));
  meta.name = 'csrf-token';
  meta.content = 'test-csrf-token';
  const availability = document.getElementById('schedule-availability');
  for (const value of ['Busy', 'Free']) {
    const option = document.createElement('option');
    option.value = value;
    availability.append(option);
  }
  availability.value = 'Busy';
  availability.defaultValue = 'Busy';
  const window = new Window(fetchImpl);
  return {document, window};
}

function fire(target, type, properties = {}) {
  return target.dispatchEvent({
    type,
    target,
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
    ...properties
  });
}

async function flush() {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
}

function jsonResponse(body, ok = true, status = 200) {
  return {ok, status, json: async () => body};
}

function deferred() {
  let resolve;
  const promise = new Promise(resolvePromise => { resolve = resolvePromise; });
  return {promise, resolve};
}

module.exports = {createDom, fire, flush, jsonResponse, deferred};
