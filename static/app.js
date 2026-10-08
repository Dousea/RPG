// DOM references
const storyDisplay = document.getElementById('story-display');
const metaChips = document.getElementById('meta-chips');
const locationStatus = document.getElementById('location-status');
const locationPlace = document.getElementById('location-place');
const deathBanner = document.getElementById('death-banner');
const locationDescription = document.getElementById('location-description');
const conditionChips = document.getElementById('condition-chips');
const goalList = document.getElementById('goal-list');
const heldList = document.getElementById('held-list');
const equipmentList = document.getElementById('equipment-list');
const inventoryList = document.getElementById('inventory-list');
const carryLoad = document.getElementById('carry-load');
const bagList = document.getElementById('bag-list');
const wornList = document.getElementById('worn-list');
const bodyList = document.getElementById('body-list');
const survivorList = document.getElementById('survivor-list');
const skillList = document.getElementById('skill-list');
const traitList = document.getElementById('trait-list');
const npcList = document.getElementById('npc-list');
const questList = document.getElementById('quest-list');
const threatList = document.getElementById('threat-list');
const barrierList = document.getElementById('barrier-list');
const corpseList = document.getElementById('corpse-list');
const roomList = document.getElementById('room-list');
const choiceOptions = document.getElementById('choice-options');
const mentionList = document.getElementById('mention-list');
const inputForm = document.getElementById('input-form');
const playerInput = document.getElementById('player-input');
const submitButton = document.getElementById('submit-button');
const resetButton = document.getElementById('reset-button');
const saveButton = document.getElementById('save-button');
const loadButton = document.getElementById('load-button');
const loadInput = document.getElementById('load-input');
const turnStatus = document.getElementById('turn-status');
const turnStep = document.getElementById('turn-step');
const turnTimer = document.getElementById('turn-timer');
const thoughts = document.getElementById('thoughts');
const thoughtsText = document.getElementById('thoughts-text');
const planScreen = document.getElementById('plan-screen');
const planSteps = document.getElementById('plan-steps');
const planGo = document.getElementById('plan-go');
const planCancel = document.getElementById('plan-cancel');

// Tracked outside applyGameOverState so handleTurn's `finally` block
// (which otherwise unconditionally re-enables input after every turn)
// knows not to revive a dead game.
let isGameOver = false;
let characterName = 'The character';

function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
}

function clearAndFill(container, nodes) {
    container.innerHTML = '';
    nodes.forEach(node => container.appendChild(node));
}

function emptyNote(text) {
    return el('p', 'empty-note', text);
}

// === Screens and tabs (docs/architecture/ui-layout.md, Screen sizes) ===
// A screen shows once the snapshot carries any of its fields, so a screen
// whose mechanic hasn't landed stays hidden without a code change here.
const SCREEN_FIELDS = {
    status: ['effects', 'conditions', 'sneaking', 'goals'],
    health: ['body'],
    inventory: ['held', 'equipment', 'inventory', 'carry'],
    clothing: ['worn'],
    character: ['character', 'skills', 'zombie_kills'],
    people: ['npcs'],
    nearby: ['threats', 'corpses', 'barriers', 'rooms'],
    quests: ['quests'],
};
const GEAR = ['Gear', ['inventory', 'clothing']];
const AROUND = ['Around', ['people', 'nearby']];
const QUESTS = ['Quests', ['quests']];
const LAYOUTS = {
    wide: Object.keys(SCREEN_FIELDS).map(id => [id.replace(/^\w/, c => c.toUpperCase()), [id]]),
    medium: [['Status', ['status', 'health']], GEAR, ['Character', ['character']], AROUND, QUESTS],
    narrow: [['You', ['status', 'health', 'character']], GEAR, AROUND, QUESTS],
};
const wideQuery = window.matchMedia('(min-width: 1200px)');
const mediumQuery = window.matchMedia('(min-width: 861px)');

const tabNav = document.getElementById('tab-nav');
const tabPanels = document.querySelector('.tab-panels');
const dossier = document.getElementById('dossier');
const screens = new Map([...document.querySelectorAll('.screen')].map(node => [node.dataset.screen, node]));
let liveScreens = new Set(['status']);
let viewedScreen = 'status';
let layoutName = null;

function currentLayout() {
    if (wideQuery.matches) return 'wide';
    return mediumQuery.matches ? 'medium' : 'narrow';
}

function liveIn(screenIds) {
    return screenIds.filter(id => liveScreens.has(id));
}

function showTab(screenIds) {
    const live = liveIn(screenIds);
    screens.forEach((node, id) => node.classList.toggle('shown', live.includes(id)));
    tabPanels.classList.toggle('stacked', live.length > 1);
    tabPanels.scrollTop = 0;
    viewedScreen = live[0] || viewedScreen;
    tabNav.querySelectorAll('.tab-btn').forEach(button => {
        button.classList.toggle('active', button.dataset.screens === screenIds.join(' '));
    });
}

// Rebuilds the tab bar for the current width, reopening the tab that holds
// the screen the player was reading.
function buildTabs() {
    layoutName = currentLayout();
    const tabs = LAYOUTS[layoutName].filter(([, ids]) => liveIn(ids).length > 0);
    tabNav.innerHTML = '';
    tabs.forEach(([label, ids]) => {
        const button = el('button', 'tab-btn', label);
        button.type = 'button';
        button.dataset.screens = ids.join(' ');
        button.addEventListener('click', () => showTab(ids));
        tabNav.appendChild(button);
    });
    const open = tabs.find(([, ids]) => ids.includes(viewedScreen)) || tabs[0];
    if (open) showTab(open[1]);
    if (layoutName !== 'narrow') setSheetOpen(false);
}

function updateLiveScreens(data) {
    const live = new Set(Object.keys(SCREEN_FIELDS).filter(id => SCREEN_FIELDS[id].some(field => field in data)));
    const changed = live.size !== liveScreens.size || [...live].some(id => !liveScreens.has(id));
    liveScreens = live;
    if (changed) buildTabs();
}

wideQuery.addEventListener('change', buildTabs);
mediumQuery.addEventListener('change', buildTabs);

// === Narrow window: header menu and the sidebar sheet ===
const menuButton = document.getElementById('menu-button');
const headerActions = document.getElementById('header-actions');
const sheetButton = document.getElementById('sheet-button');

function setMenuOpen(open) {
    headerActions.classList.toggle('open', open);
    menuButton.setAttribute('aria-expanded', String(open));
}

function setSheetOpen(open) {
    dossier.classList.toggle('open', open);
    sheetButton.setAttribute('aria-expanded', String(open));
}

menuButton.addEventListener('click', () => setMenuOpen(!headerActions.classList.contains('open')));
headerActions.addEventListener('click', () => setMenuOpen(false));
sheetButton.addEventListener('click', () => setSheetOpen(!dossier.classList.contains('open')));
document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        setSheetOpen(false);
        setMenuOpen(false);
    }
});

// A downward swipe that starts on the handle or the tab bar closes the sheet;
// starting on the panels it would fight their scrolling.
let swipeStartY = null;
dossier.addEventListener('touchstart', event => {
    const onGrip = event.target.closest('.sheet-handle, .tab-nav');
    swipeStartY = onGrip ? event.touches[0].clientY : null;
}, { passive: true });
dossier.addEventListener('touchend', event => {
    if (swipeStartY !== null && event.changedTouches[0].clientY - swipeStartY > 60) {
        setSheetOpen(false);
    }
    swipeStartY = null;
});

// === Section renderers ===

function capitalised(text) {
    return (text || '').replace(/^\w/, c => c.toUpperCase());
}

function renderMetaChips(data) {
    metaChips.innerHTML = '';
    metaChips.appendChild(el('span', 'day', `Day ${data.day}`));
    metaChips.appendChild(el('span', null, capitalised(data.time_of_day)));
    if (data.weather) {
        const w = data.weather;
        metaChips.appendChild(el('span', null, `${capitalised(w.summary)}, ${w.temperature_c} °C${w.sheltered ? ', sheltered' : ''}`));
    }
    metaChips.appendChild(data.outbreak_day
        ? el('span', 'tag bad', `Outbreak day ${data.outbreak_day}`)
        : el('span', null, 'Before the outbreak'));
}

// The triage code (style.css): green fine, yellow watch, red urgent, black grave.
function effectTone(effect) {
    if (effect.type === 'food_eaten') return 'good';
    if (effect.level >= 4) return 'grave';
    return effect.level >= 3 ? 'bad' : 'warn';
}

function tag(text, tone) {
    return el('span', tone ? `tag ${tone}` : 'tag', text);
}

function renderCondition(data) {
    conditionChips.innerHTML = '';
    (data.effects || []).forEach(effect => conditionChips.appendChild(tag(effect.name, effectTone(effect))));
    (data.conditions || []).forEach(condition => conditionChips.appendChild(tag(capitalised(condition), 'bad')));
    if (data.sneaking) conditionChips.appendChild(tag('Sneaking'));
    if (!conditionChips.hasChildNodes()) conditionChips.appendChild(emptyNote('Nothing troubling you.'));
}

function renderGoals(data) {
    const goals = data.goals || { short_term: [], long_term: [] };
    const groups = [
        ['Short-term', goals.short_term || []],
        ['Long-term', goals.long_term || []],
    ];
    goalList.innerHTML = '';
    const anyGoals = groups.some(([, items]) => items.length > 0);
    if (!anyGoals) {
        goalList.appendChild(emptyNote('Nothing set yet.'));
        return;
    }
    groups.forEach(([label, items]) => {
        if (items.length === 0) return;
        const group = el('div', 'goal-group');
        group.appendChild(el('h4', null, label));
        const ul = el('ul');
        items.forEach(item => ul.appendChild(el('li', null, item)));
        group.appendChild(ul);
        goalList.appendChild(group);
    });
}

function renderInventory(data) {
    const items = data.inventory || [];
    if (items.length === 0) {
        clearAndFill(inventoryList, [emptyNote('Nothing carried.')]);
        return;
    }
    clearAndFill(inventoryList, items.map(item => {
        const li = el('li', 'row-item');
        li.appendChild(el('span', null, item.count > 1 ? `${item.name} x${item.count}` : item.name));
        li.appendChild(el('span', 'value muted', item.condition));
        return li;
    }));
}

// Carried weight against what the player can carry (numbers are allowed here), and each bag with what is in it.
function renderCarry(data) {
    const load = data.carry;
    if (!load) return;
    carryLoad.textContent = `${load.weight} kg of ${load.max_weight} kg `;
    if (load.level > 0) {
        const name = ['', 'Weighed Down', 'Overloaded', 'Very Overloaded', 'Extremely Overloaded'][load.level];
        carryLoad.appendChild(tag(name, effectTone({ type: 'heavy_load', level: load.level })));
    }
    if (load.bags.length === 0) {
        clearAndFill(bagList, [emptyNote('No bags.')]);
        return;
    }
    clearAndFill(bagList, load.bags.map(bag => {
        const li = el('li', 'row-item');
        const who = el('span', 'who');
        who.appendChild(el('span', null, bag.name));
        who.appendChild(el('span', 'aside', bag.contents.length ? bag.contents.join(', ') : 'Empty'));
        li.appendChild(who);
        li.appendChild(el('span', 'value muted', bag.place));
        return li;
    }));
}

function renderHeld(data) {
    const held = data.held;
    if (!held) {
        clearAndFill(heldList, [emptyNote('Nothing in hand.')]);
        return;
    }
    const li = el('li', 'row-item');
    li.appendChild(el('span', 'label', held.name));
    li.appendChild(el('span', 'value muted', held.condition_word));
    clearAndFill(heldList, [li]);
}

function renderEquipment(data) {
    const slots = data.equipment || [];
    clearAndFill(equipmentList, slots.map(slot => {
        const li = el('li', 'row-item');
        li.appendChild(el('span', 'label', slot.slot));
        if (slot.both_hands) {
            li.appendChild(el('span', 'value muted', 'Two-handed grip'));
        } else {
            li.appendChild(el('span', slot.item ? 'value' : 'value muted', slot.item ? `${slot.item} (${slot.condition})` : 'Empty'));
        }
        return li;
    }));
}

function renderWorn(data) {
    const worn = data.worn || [];
    if (worn.length === 0) {
        clearAndFill(wornList, [emptyNote('Nothing worn.')]);
        return;
    }
    clearAndFill(wornList, worn.map(piece => {
        const li = el('li', 'row-item');
        li.appendChild(el('span', 'label', piece.location.replace('base:', '').replace(/_/g, ' ')));
        li.appendChild(el('span', 'value', piece.wetness_word ? `${piece.name} (${piece.wetness_word})` : piece.name));
        return li;
    }));
}

function renderBody(data) {
    const parts = data.body || [];
    if (parts.length === 0) {
        clearAndFill(bodyList, [emptyNote('No wounds.')]);
        return;
    }
    clearAndFill(bodyList, parts.map(part => {
        const tags = part.wounds.map(wound => tag(wound));
        if (part.bleeding) tags.push(tag('bleeding', 'bad'));
        if (part.bandaged) tags.push(part.dirty ? tag('dirty bandage', 'warn') : tag('bandaged', 'good'));
        if (part.infected) tags.push(tag('infected', 'bad'));
        const li = el('li', 'row-item');
        li.appendChild(el('span', null, capitalised(part.part)));
        const row = el('span', 'tag-row');
        tags.forEach(node => row.appendChild(node));
        li.appendChild(row);
        return li;
    }));
}

function renderSurvivor(data) {
    const character = data.character || {};
    const rows = [['Name', character.name], ['Occupation', character.occupation]];
    if (typeof data.zombie_kills === 'number') rows.push(['Zombies killed', String(data.zombie_kills)]);
    clearAndFill(survivorList, rows.filter(([, value]) => value).map(([label, value]) => {
        const li = el('li', 'row-item');
        li.appendChild(el('span', 'label', label));
        li.appendChild(el('span', 'value', value));
        return li;
    }));
}

// Skills with a level or some progress, grouped by category; the bar is
// the share of the way to the next level, never the XP itself.
function renderSkills(data) {
    const trained = (data.skills || []).filter(skill => skill.level > 0 || skill.progress > 0);
    if (trained.length === 0) {
        clearAndFill(skillList, [emptyNote('No skills yet.')]);
        return;
    }
    const groups = [];
    trained.forEach(skill => {
        let group = groups.find(entry => entry.category === skill.category);
        if (!group) {
            group = { category: skill.category, skills: [] };
            groups.push(group);
        }
        group.skills.push(skill);
    });
    clearAndFill(skillList, groups.map(group => {
        const wrapper = el('div', 'skill-group');
        wrapper.appendChild(el('div', 'skill-category', group.category));
        group.skills.forEach(skill => {
            const row = el('div', 'skill-row');
            row.appendChild(el('span', 'label', skill.name));
            row.appendChild(el('span', 'value', String(skill.level)));
            const bar = el('div', 'skill-bar');
            const fill = el('div', 'skill-fill');
            fill.style.width = `${Math.round(skill.progress * 100)}%`;
            bar.appendChild(fill);
            row.appendChild(bar);
            wrapper.appendChild(row);
        });
        return wrapper;
    }));
}

function renderNamedEntries(container, entries, emptyLabel) {
    if (!entries || entries.length === 0) {
        clearAndFill(container, [emptyNote(emptyLabel)]);
        return;
    }
    clearAndFill(container, entries.map(entry => {
        const wrapper = el('div', 'named-entry');
        wrapper.appendChild(el('div', 'name', entry.name));
        wrapper.appendChild(el('div', 'desc', entry.description));
        return wrapper;
    }));
}

// Disposition bands are colored the same way the narrator reads them --
// The player can tell Emma has warmed to them, never the raw affinity number.
const DISPOSITION_TONE = {
    loyal: 'good', friendly: 'good',
    neutral: '',
    wary: 'warn', hostile: 'bad', terrified: 'bad', hated: 'grave',
};

function renderNpcs(data) {
    const npcs = data.npcs || [];
    if (npcs.length === 0) {
        clearAndFill(npcList, [emptyNote('No one else is here.')]);
        return;
    }
    clearAndFill(npcList, npcs.map(npc => {
        const li = el('li', 'row-item');
        const who = el('span', 'who');
        who.appendChild(el('span', null, npc.name));
        who.appendChild(el('span', 'aside', `Trust ${npc.trust}`));
        li.appendChild(who);
        const tags = el('span', 'tag-row');
        if (npc.following) tags.appendChild(tag('following you'));
        tags.appendChild(tag(npc.disposition, DISPOSITION_TONE[npc.disposition]));
        li.appendChild(tags);
        return li;
    }));
}

function threatTone(threat) {
    if (threat.state_word === 'down') return '';
    if (threat.distance_word === 'on you' || /attacking|behind/.test(threat.state_word)) return 'grave';
    return /coming|crawling toward/.test(threat.state_word) ? 'bad' : 'warn';
}

function renderThreats(data) {
    const threats = data.threats || [];
    if (threats.length === 0) {
        clearAndFill(threatList, [emptyNote('Nothing threatening in sight.')]);
        return;
    }
    clearAndFill(threatList, threats.map(threat => {
        const li = el('li', 'row-item');
        const who = el('span', 'who');
        who.appendChild(el('span', null, threat.label ? capitalised(threat.label) : 'Something unseen'));
        if (threat.distance_word) who.appendChild(el('span', 'aside', capitalised(threat.distance_word)));
        li.appendChild(who);
        li.appendChild(tag(threat.state_word, threatTone(threat)));
        return li;
    }));
}

// A body shows its distance, how far gone it is and, once searched, what it held.
function renderCorpses(data) {
    const corpses = data.corpses || [];
    if (corpses.length === 0) {
        clearAndFill(corpseList, [emptyNote('No bodies in sight.')]);
        return;
    }
    clearAndFill(corpseList, corpses.map(corpse => {
        const li = el('li', 'row-item');
        const who = el('span', 'who');
        who.appendChild(el('span', null, corpse.carried ? 'The body you carry' : capitalised(corpse.label)));
        who.appendChild(el('span', 'aside', capitalised(corpse.distance_word)));
        if (corpse.searched) {
            const held = corpse.contents.length ? corpse.contents.map(capitalised).join(', ') : 'Nothing left';
            who.appendChild(el('span', 'aside', held));
        }
        li.appendChild(who);
        const tags = el('span', 'tag-row');
        tags.appendChild(tag(capitalised(corpse.rot_word), ''));
        tags.appendChild(tag(corpse.searched ? 'Searched' : 'Not searched', corpse.searched ? 'good' : ''));
        li.appendChild(tags);
        return li;
    }));
}

// Each room of the zone with its furniture: a container shows what is in it only once it has been gone through.
function renderRooms(data) {
    const rooms = data.rooms || [];
    if (rooms.length === 0) {
        clearAndFill(roomList, [emptyNote('No rooms to search here.')]);
        return;
    }
    clearAndFill(roomList, rooms.map(room => {
        const li = el('li', 'row-item');
        const who = el('span', 'who');
        who.appendChild(el('span', null, capitalised(room.name)));
        room.containers.forEach(container => {
            const held = container.contents.length ? container.contents.map(capitalised).join(', ') : 'Empty';
            const note = container.opened ? `${capitalised(container.name)}: ${held}` : `${capitalised(container.name)}: not searched`;
            who.appendChild(el('span', 'aside', note));
        });
        li.appendChild(who);
        if (room.here) li.appendChild(tag('You are here', 'good'));
        return li;
    }));
}

function plankWords(count, where) {
    return `${count} plank${count === 1 ? '' : 's'} ${where}`;
}

function renderBarriers(data) {
    const barriers = data.barriers || [];
    if (barriers.length === 0) {
        clearAndFill(barrierList, [emptyNote('No doors or windows here.')]);
        return;
    }
    clearAndFill(barrierList, barriers.map(barrier => {
        const li = el('li', 'row-item');
        const who = el('span', 'who');
        who.appendChild(el('span', null, capitalised(barrier.name)));
        const planks = [];
        if (barrier.planks_here) planks.push(plankWords(barrier.planks_here, 'on this side'));
        if (barrier.planks_far) planks.push(plankWords(barrier.planks_far, 'on the far side'));
        if (planks.length) who.appendChild(el('span', 'aside', planks.join(', ')));
        li.appendChild(who);
        const tags = el('span', 'tag-row');
        tags.appendChild(tag(capitalised(barrier.state_word), /broken|smashed/.test(barrier.state_word) ? 'bad' : ''));
        if (barrier.thumping) tags.appendChild(tag('Pounding', 'grave'));
        li.appendChild(tags);
        return li;
    }));
}

function renderQuests(data) {
    const quests = data.quests || [];
    if (quests.length === 0) {
        clearAndFill(questList, [emptyNote('No active quests.')]);
        return;
    }
    clearAndFill(questList, quests.map(quest => {
        const wrapper = el('div', 'quest');
        wrapper.appendChild(el('div', 'quest-title', quest.title));
        (quest.objectives || []).forEach(objective => {
            const row = el('div', `quest-objective ${objective.done ? 'done' : ''}`.trim());
            row.appendChild(el('span', 'glyph', objective.done ? '☑' : '☐'));
            row.appendChild(el('span', null, objective.label));
            wrapper.appendChild(row);
        });
        return wrapper;
    }));
}

// Renders the narrator's suggested next moves as buttons, alongside (never
// instead of) the free-text input. Picking one just fills the input and
// submits it through the normal /play path -- the parser can't tell a
// clicked suggestion from something the player typed themselves.
function renderChoiceOptions(data) {
    const options = data.options || [];
    clearAndFill(choiceOptions, options.map(optionText => {
        const button = el('button', 'choice-option', optionText);
        button.type = 'button';
        button.addEventListener('click', () => {
            playerInput.textContent = optionText;
            inputForm.requestSubmit();
        });
        return button;
    }));
}

// Append one story beat. Player input is set as text, never HTML, so a
// '<' in what the player types cannot break out into markup.
function appendStory(playerText, storyText) {
    const paragraph = el('p', 'beat');
    if (playerText) paragraph.appendChild(el('span', 'echo', playerText));
    paragraph.appendChild(document.createTextNode(storyText));
    storyDisplay.appendChild(paragraph);
    storyDisplay.scrollTop = storyDisplay.scrollHeight;
}

// Shows/hides the death banner and locks down input once the character is dead.
// Nothing re-enables these here -- the reset flow reloads the page,
// which is what actually clears this state.
function applyGameOverState(data) {
    isGameOver = !!data.game_over;
    // LLM-adjacent text (the fact that killed the character) -- textContent
    // only, never innerHTML.
    deathBanner.innerHTML = '';
    if (isGameOver) {
        deathBanner.appendChild(el('span', 'death-name', `${characterName} has died.`));
        if (data.death_cause) deathBanner.appendChild(el('span', 'death-cause', data.death_cause));
    }
    deathBanner.hidden = !isGameOver;
    setInputEnabled(!isGameOver);
    submitButton.disabled = isGameOver;
    choiceOptions.querySelectorAll('button').forEach(button => {
        button.disabled = isGameOver;
    });
}

// Refresh the dossier panel from a state payload.
function updatePanel(data) {
    if (data.needs_creation) {
        openCreation();
        return;
    }
    characterName = (data.character && data.character.name) || characterName;
    locationStatus.textContent = data.current_location;
    // LLM-authored free text -- textContent only, never innerHTML.
    locationPlace.textContent = capitalised(data.current_place);
    locationPlace.hidden = !data.current_place;
    locationDescription.textContent = data.location_description || '';
    renderMetaChips(data);
    renderCondition(data);
    renderGoals(data);
    renderInventory(data);
    renderCarry(data);
    renderHeld(data);
    renderEquipment(data);
    renderWorn(data);
    renderBody(data);
    renderSurvivor(data);
    renderSkills(data);
    renderNamedEntries(traitList, data.traits, 'None recorded.');
    renderNpcs(data);
    renderThreats(data);
    renderCorpses(data);
    renderRooms(data);
    renderBarriers(data);
    renderQuests(data);
    renderChoiceOptions(data);
    renderPlan(data);
    setMentions(data);
    applyGameOverState(data);
    updateLiveScreens(data);
}

function updateUI(data, playerText) {
    if (data.story_text) {
        appendStory(playerText, data.story_text);
    }
    updatePanel(data);
    if (data.plan) focusPlan();
}

// === The plan screen ===
// A plan whose targets fit more than one thing comes back in place of a story:
// each step in words, a picker (radio group) under each step that waits on an
// answer, and Go / Cancel. Go sends one candidate id per picker, in order. All
// text is the engine's words, set as text, never HTML.

function planPicker(choice, number, stepText) {
    const group = el('fieldset', 'plan-picker');
    group.appendChild(el('legend', 'plan-legend', `Which one: ${stepText}`));

    choice.candidates.forEach(candidate => {
        const label = el('label', 'plan-option');

        const radio = el('input');
        radio.type = 'radio';
        radio.name = `plan-choice-${number}`;
        radio.value = candidate.id;
        radio.addEventListener('change', updatePlanGo);
        label.appendChild(radio);

        const words = el('span', 'plan-words');
        words.appendChild(el('span', 'plan-name', candidate.name));
        if (candidate.description) words.appendChild(el('span', 'plan-detail', candidate.description));
        label.appendChild(words);

        group.appendChild(label);
    });

    return group;
}

function planStep(step, plan) {
    const item = el('li', step.done ? 'plan-step done' : 'plan-step');
    item.appendChild(el('span', 'plan-sr', step.done ? 'Done: ' : 'To do: '));
    const mark = el('span', 'plan-mark', step.done ? '✓' : '·');
    mark.setAttribute('aria-hidden', 'true');
    item.appendChild(mark);
    item.appendChild(el('span', 'plan-text', step.text));
    if (step.default) item.appendChild(el('span', 'plan-default', step.default));
    if (step.choice !== null) item.appendChild(planPicker(plan.choices[step.choice], step.choice, step.text));
    return item;
}

function planAnswers() {
    const groups = planSteps.querySelectorAll('.plan-picker');
    return Array.from(groups, group => {
        const checked = group.querySelector('input:checked');
        return checked ? checked.value : null;
    });
}

function updatePlanGo() {
    planGo.disabled = planAnswers().some(answer => answer === null);
}

function renderPlan(data) {
    const plan = data.plan;
    planScreen.hidden = !plan;
    clearAndFill(planSteps, plan ? plan.steps.map(step => planStep(step, plan)) : []);
    updatePlanGo();
}

// Puts the keyboard on the first question, or on Go when there is none to answer.
function focusPlan() {
    const first = planSteps.querySelector('input[type="radio"]');
    (first || planGo).focus();
}

async function handlePlanCancel() {
    try {
        const response = await fetch('/plan/cancel', { method: 'POST' });
        if (response.ok) updatePanel(await response.json());
    } catch (error) {
        console.error('Could not cancel the plan:', error);
    }
    playerInput.focus();
}

async function handlePlanGo() {
    if (planGo.disabled) return;
    await runTurn('/plan/go/stream', { choices: planAnswers() }, 'Go', false);
}

planGo.addEventListener('click', handlePlanGo);
planCancel.addEventListener('click', handlePlanCancel);
planScreen.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
        event.preventDefault();
        handlePlanCancel();
    }
});

function showSystemError(message) {
    storyDisplay.appendChild(el('p', 'beat system-error', `The turn didn't go through (${message}). Try the action again.`));
    storyDisplay.scrollTop = storyDisplay.scrollHeight;
}

// What the status line says for each step /play/stream reports.
const STEP_LABELS = {
    parsing: 'Parsing…',
    checking_plan: 'Checking the plan…',
    thinking: 'Thinking…',
    narrating: 'Narrating…',
    fact_checking: 'Fact checking…',
    rewriting: 'Rewriting…',
    options: 'Writing options…',
    saving: 'Saving…',
};

// The turn in progress: its status line, timer and the story beat being written.
const liveTurn = { step: null, stepStartedAt: 0, timerId: null, beat: null, storyNode: null, playerText: '' };

function setStep(step) {
    liveTurn.step = step;
    liveTurn.stepStartedAt = Date.now();
    turnStep.textContent = STEP_LABELS[step] || '';
    turnTimer.textContent = '';
}

function startTurnStatus(playerText) {
    liveTurn.playerText = playerText;
    thoughtsText.textContent = '';
    thoughts.open = false;
    thoughts.hidden = true;
    turnStatus.hidden = false;
    setStep('parsing');
    liveTurn.timerId = setInterval(() => {
        const seconds = Math.floor((Date.now() - liveTurn.stepStartedAt) / 1000);
        turnTimer.textContent = seconds >= 1 ? `${seconds} s` : '';
    }, 250);
}

function clearLiveBeat() {
    if (liveTurn.beat) liveTurn.beat.remove();
    liveTurn.beat = null;
    liveTurn.storyNode = null;
}

function stopTurnStatus() {
    clearInterval(liveTurn.timerId);
    liveTurn.timerId = null;
    clearLiveBeat();
    turnStatus.hidden = true;
}

// The story so far replaces the live beat's text; the finished turn replaces the beat.
function showStorySoFar(text) {
    if (!liveTurn.beat) {
        liveTurn.beat = el('p', 'beat');
        liveTurn.beat.appendChild(el('span', 'echo', liveTurn.playerText));
        liveTurn.storyNode = document.createTextNode('');
        liveTurn.beat.appendChild(liveTurn.storyNode);
        storyDisplay.appendChild(liveTurn.beat);
    }
    // LLM-authored text -- a text node, never HTML.
    liveTurn.storyNode.nodeValue = text;
    storyDisplay.scrollTop = storyDisplay.scrollHeight;
}

// Handles one event from /play/stream; returns the finished turn's payload on "done".
function handleTurnEvent(event) {
    if (event.type === 'step') {
        if (event.step === 'rewriting') {
            clearLiveBeat();
            thoughtsText.textContent = '';
        }
        setStep(event.step);
    } else if (event.type === 'thinking') {
        // A rewrite keeps its own label while it thinks and writes.
        if (liveTurn.step === 'narrating' && !liveTurn.beat) setStep('thinking');
        thoughts.hidden = false;
        thoughtsText.textContent += event.text;
        if (thoughts.open) thoughtsText.scrollTop = thoughtsText.scrollHeight;
    } else if (event.type === 'story') {
        if (liveTurn.step === 'thinking') setStep('narrating');
        showStorySoFar(event.text);
    } else if (event.type === 'done') {
        return event.turn;
    } else if (event.type === 'error') {
        throw new Error(event.message || 'the turn failed');
    }
    return null;
}

// Reads /play/stream's JSON lines as they arrive; resolves with the finished turn.
async function readTurnStream(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let newline;
        while ((newline = buffer.indexOf('\n')) >= 0) {
            const line = buffer.slice(0, newline).trim();
            buffer = buffer.slice(newline + 1);
            if (!line) continue;
            const turn = handleTurnEvent(JSON.parse(line));
            if (turn) return turn;
        }
    }
    throw new Error('the turn stopped before it finished');
}

// === The @ list ===
// Typing "@" opens a list of what the engine says is in reach (data.mentions).
// A pick puts a chip into the input: a non-editable token that deletes as one
// unit. The turn sends the text with a mark where each chip stood plus the
// picked ids in order, so the engine binds the entity itself. "@" text with no
// pick is plain prose.

const MENTION_MARK = '￼';
const MENTION_KINDS = [
    ['zombie', 'Zombies'],
    ['corpse', 'Bodies'],
    ['npc', 'People'],
    ['barrier', 'Doors and windows'],
    ['room', 'Rooms'],
    ['container', 'Containers'],
    ['zone', 'Places'],
    ['body_part', 'Your body'],
    ['item', 'Items'],
];

let mentionEntries = [];
let mentionShown = [];
let mentionActive = 0;

function setMentions(data) {
    mentionEntries = data.mentions || [];
    closeMentions();
}

function setInputEnabled(enabled) {
    playerInput.contentEditable = enabled ? 'plaintext-only' : 'false';
    playerInput.setAttribute('aria-disabled', String(!enabled));
}

// The "@..." being typed at the caret (in a text run, never inside a chip), or null when there is none.
function mentionQuery() {
    const selection = window.getSelection();
    if (!selection.rangeCount || !selection.isCollapsed) return null;
    const node = selection.anchorNode;
    if (!node || node.nodeType !== Node.TEXT_NODE || !playerInput.contains(node)) return null;
    if (node.parentElement !== playerInput) return null;
    const end = selection.anchorOffset;
    const before = node.data.slice(0, end);
    const start = before.lastIndexOf('@');
    if (start < 0 || (start > 0 && !/\s/.test(before[start - 1]))) return null;
    return { node, start, end, text: before.slice(start + 1) };
}

function closeMentions() {
    mentionShown = [];
    mentionList.hidden = true;
    mentionList.innerHTML = '';
    playerInput.setAttribute('aria-expanded', 'false');
    playerInput.removeAttribute('aria-activedescendant');
}

function setActiveMention(index) {
    mentionActive = (index + mentionShown.length) % mentionShown.length;
    mentionList.querySelectorAll('.mention-option').forEach((node, i) => {
        node.setAttribute('aria-selected', String(i === mentionActive));
        if (i === mentionActive) {
            playerInput.setAttribute('aria-activedescendant', node.id);
            node.scrollIntoView({ block: 'nearest' });
        }
    });
}

function refreshMentions() {
    const query = mentionQuery();
    if (!query) return closeMentions();
    const words = query.text.toLowerCase().split(/\s+/).filter(Boolean);
    const kindLabel = new Map(MENTION_KINDS);
    mentionShown = mentionEntries.filter(entry => {
        const haystack = `${entry.label} ${entry.description} ${kindLabel.get(entry.kind)}`.toLowerCase();
        return words.every(word => haystack.includes(word));
    });
    if (!mentionShown.length) return closeMentions();
    mentionList.innerHTML = '';
    let index = 0;
    MENTION_KINDS.forEach(([kind, heading]) => {
        const group = mentionShown.filter(entry => entry.kind === kind);
        if (!group.length) return;
        const headingNode = el('li', 'mention-kind', heading);
        headingNode.setAttribute('role', 'presentation');
        headingNode.setAttribute('aria-hidden', 'true');
        mentionList.appendChild(headingNode);
        group.forEach(entry => {
            const optionIndex = index++;
            const option = el('li', 'mention-option');
            option.id = `mention-option-${optionIndex}`;
            option.setAttribute('role', 'option');
            option.setAttribute('aria-label', `${heading}: ${entry.label}`);
            option.appendChild(el('span', 'mention-name', entry.label));
            if (entry.description) option.appendChild(el('span', 'mention-detail', entry.description));
            option.addEventListener('click', () => pickMention(entry));
            mentionList.appendChild(option);
        });
    });
    // The list reads in group order, so the entries do too.
    mentionShown = MENTION_KINDS.flatMap(([kind]) => mentionShown.filter(entry => entry.kind === kind));
    mentionList.hidden = false;
    playerInput.setAttribute('aria-expanded', 'true');
    setActiveMention(0);
}

function pickMention(entry) {
    const query = mentionQuery();
    if (!query) return;
    const chip = el('span', 'mention-chip', `@${entry.label}`);
    chip.contentEditable = 'false';
    chip.dataset.id = entry.id;
    const rest = query.node.splitText(query.end);
    query.node.deleteData(query.start, query.end - query.start);
    query.node.after(chip);
    rest.data = ` ${rest.data}`;
    const range = document.createRange();
    range.setStart(rest, 1);
    range.collapse(true);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    closeMentions();
    playerInput.focus();
}

// The input's text with a mark where each chip stands, and the chips' ids in text order.
function pinnedInput() {
    let input = '';
    const mentions = [];
    playerInput.childNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE && node.classList.contains('mention-chip')) {
            input += MENTION_MARK;
            mentions.push(node.dataset.id);
        } else {
            input += node.textContent.replaceAll(MENTION_MARK, '');
        }
    });
    return { input: input.trim(), mentions };
}

playerInput.addEventListener('input', refreshMentions);
playerInput.addEventListener('click', refreshMentions);
playerInput.addEventListener('keyup', event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) refreshMentions();
});
playerInput.addEventListener('blur', closeMentions);
// The input holds one line of plain text and chips: nothing pasted or dropped brings markup in.
playerInput.addEventListener('paste', event => {
    event.preventDefault();
    const text = event.clipboardData.getData('text/plain').replace(/\s+/g, ' ');
    document.execCommand('insertText', false, text);
});
playerInput.addEventListener('drop', event => event.preventDefault());
playerInput.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
        event.preventDefault();
        if (event.isComposing || !playerInput.isContentEditable) return;
        if (!mentionList.hidden) pickMention(mentionShown[mentionActive]);
        else inputForm.requestSubmit();
        return;
    }
    if (mentionList.hidden) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        setActiveMention(mentionActive + (event.key === 'ArrowDown' ? 1 : -1));
    } else if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeMentions();
    }
});
// Keeps the input focused, so a click on the list does not blur and close it first.
mentionList.addEventListener('mousedown', event => event.preventDefault());

// Function to handle form submission
async function handleTurn(event) {
    event.preventDefault();
    const sent = pinnedInput();
    if (!sent.input) return;
    await runTurn('/play/stream', sent, playerInput.textContent.trim(), true);
}

// Sends a turn to a streaming route and shows it; `typed` turns also clear the input they came from.
async function runTurn(url, sent, inputText, typed) {
    planScreen.hidden = true;
    setInputEnabled(false);
    submitButton.disabled = true;
    submitButton.textContent = 'Wait…';
    choiceOptions.querySelectorAll('button').forEach(button => { button.disabled = true; });
    startTurnStatus(inputText);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sent)
        });

        if (!response.ok) {
            throw new Error(`Server responded with status: ${response.status}`);
        }

        const data = await readTurnStream(response);
        stopTurnStatus();
        updateUI(data, inputText);

    } catch (error) {
        console.error('Error during game turn:', error);
        stopTurnStatus();
        showSystemError(error.message);
    } finally {
        if (typed) {
            playerInput.textContent = '';
            closeMentions();
        }
        submitButton.textContent = 'Act';
        // A dead game stays locked down -- updateUI already applied that
        // via applyGameOverState, so this must not undo it.
        if (!isGameOver) {
            setInputEnabled(true);
            if (planScreen.hidden) playerInput.focus();
            else focusPlan();
            submitButton.disabled = false;
            // On success updateUI already re-rendered fresh (enabled)
            // option buttons; on failure the stale ones from before the
            // click need re-enabling by hand since nothing replaced them.
            choiceOptions.querySelectorAll('button').forEach(button => { button.disabled = false; });
        }
    }
}

// Function to reset the game
async function handleReset() {
    if (!confirm('Are you sure you want to reset the game? All progress will be lost.')) {
        return;
    }
    try {
        const response = await fetch('/reset', { method: 'POST' });
        const data = await response.json();
        alert(data.message);
        window.location.reload();
    } catch (error) {
        console.error('Error resetting game:', error);
        alert('Failed to reset the game.');
    }
}

// Downloads the current save as a file; the browser handles the prompt.
function handleSave() {
    window.location.href = '/save/export';
}

// Opens the file picker; the actual upload happens in handleLoadFile once
// a file is chosen.
function handleLoad() {
    loadInput.value = '';
    loadInput.click();
}

async function handleLoadFile() {
    const file = loadInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('save', file);

    try {
        const response = await fetch('/save/import', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) {
            alert(data.error || 'Could not load that save.');
            return;
        }
        storyDisplay.innerHTML = '';
        appendStory(null, 'Save loaded.');
        updatePanel(data);
    } catch (error) {
        console.error('Error loading save:', error);
        alert('Failed to load that save file.');
    }
}

// Load the real world state so a reloaded page is not showing defaults.
async function loadState() {
    try {
        const response = await fetch('/state');
        if (!response.ok) return;
        updatePanel(await response.json());
    } catch (error) {
        console.error('Could not load game state:', error);
    }
}

// === Character creation ===
// The points and skills shown here are a convenience; the server checks the build again.
const creationScreen = document.getElementById('creation-screen');
const cc = id => document.getElementById('cc-' + id);
let creationData = null;

function fillSelect(select, options) {
    select.innerHTML = '';
    options.forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    });
}

function traitById(id) {
    const t = creationData.traits;
    return [...t.good, ...t.bad, ...t.granted].find(trait => trait.id === id);
}

function currentOccupation() {
    return creationData.occupations.find(o => o.id === cc('occupation').value);
}

function chosenTraits() {
    return [...document.querySelectorAll('#cc-good input, #cc-bad input')]
        .filter(box => box.checked).map(box => box.value);
}

function clashes(a, b) {
    return traitById(a).excludes.includes(b) || traitById(b).excludes.includes(a);
}

function refreshCreation() {
    const occupation = currentOccupation();
    const granted = occupation.granted_traits;
    document.querySelectorAll('#cc-good input, #cc-bad input').forEach(box => {
        const others = [...granted, ...chosenTraits().filter(id => id !== box.value)];
        box.disabled = !box.checked && others.some(other => clashes(box.value, other));
    });
    const chosen = chosenTraits();
    const points = occupation.cost - chosen.reduce((sum, id) => sum + traitById(id).cost, 0);
    const short = points < creationData.min_points_to_accept;
    cc('points').textContent = `${points} points left` + (short ? ', take a weakness or drop a strength' : '');
    cc('points').classList.toggle('short', short);
    cc('granted').textContent = granted.length
        ? 'Comes with: ' + granted.map(id => traitById(id).name).join(', ') : '';
    cc('title-row').hidden = occupation.id !== 'unemployed';
    cc('beard-row').hidden = cc('gender').value !== 'male';
    const lim = creationData.skill_limits;
    const levels = {};
    Object.keys(creationData.skills).forEach(s => { levels[s] = creationData.base_skills[s] || 0; });
    [occupation.boosts, ...[...granted, ...chosen].map(id => traitById(id).boosts)].forEach(boosts => {
        Object.entries(boosts).forEach(([skill, amount]) => { levels[skill] += amount; });
    });
    const shown = Object.entries(levels)
        .map(([skill, level]) => [skill, Math.max(lim.min, Math.min(lim.max, level))])
        .filter(([skill, level]) => level > 0);
    cc('skills').textContent = shown.map(([skill, level]) => `${creationData.skills[skill]} ${level}`).join(', ');
    refreshOutfit();
}

function refreshOutfit(keep) {
    const data = creationData;
    const gender = cc('gender').value;
    const allowed = new Set();
    const lists = [data.outfits.default[gender]];
    const occupationLists = data.outfits.occupations[cc('occupation').value];
    if (occupationLists) lists.push(occupationLists[gender]);
    chosenTraits().forEach(id => {
        const traitLists = data.outfits.traits[id];
        if (traitLists) lists.push(traitLists[gender]);
    });
    lists.forEach(list => Object.values(list).forEach(entries => entries.forEach(e => allowed.add(e.item_id))));
    Object.values(data.presets).forEach(p => p.outfit.forEach(id => allowed.add(id)));
    const previous = keep || selectedOutfit();
    const byLocation = {};
    [...allowed].forEach(id => {
        const item = data.clothing_items[id];
        (byLocation[item.location] = byLocation[item.location] || []).push([id, item.name]);
    });
    cc('outfit').innerHTML = '';
    Object.entries(byLocation).forEach(([location, items]) => {
        const label = el('label', 'field', location.replace('base:', '').replace(/_/g, ' '));
        const select = document.createElement('select');
        select.dataset.location = location;
        fillSelect(select, [['', 'None'], ...items]);
        select.value = items.some(([id]) => previous.includes(id)) ? previous.find(id => items.some(([i]) => i === id)) : '';
        label.appendChild(select);
        cc('outfit').appendChild(label);
    });
}

function selectedOutfit() {
    return [...document.querySelectorAll('#cc-outfit select')].map(s => s.value).filter(Boolean);
}

function dropClashingTraits() {
    const granted = currentOccupation().granted_traits;
    document.querySelectorAll('#cc-good input, #cc-bad input').forEach(box => {
        if (box.checked && granted.some(other => clashes(box.value, other))) box.checked = false;
    });
}

function buildFromForm() {
    return {
        appearance: {
            forename: cc('forename').value.trim(),
            surname: cc('surname').value.trim(),
            gender: cc('gender').value,
            skin_tone: Number(cc('skin').value),
            hair_style: cc('hair-style').value,
            hair_colour: cc('hair-colour').value,
            beard_style: cc('gender').value === 'male' ? cc('beard').value : '',
            backstory: cc('backstory').value.trim(),
        },
        occupation_id: cc('occupation').value,
        job_title: currentOccupation().id === 'unemployed' ? cc('title').value.trim() : '',
        traits: chosenTraits(),
        outfit: selectedOutfit(),
    };
}

function fillFromPreset(preset) {
    const a = preset.appearance;
    cc('forename').value = a.forename;
    cc('surname').value = a.surname;
    cc('gender').value = a.gender;
    cc('skin').value = String(a.skin_tone);
    cc('hair-style').value = a.hair_style;
    cc('hair-colour').value = a.hair_colour;
    cc('beard').value = a.beard_style;
    cc('backstory').value = a.backstory;
    cc('occupation').value = preset.occupation_id;
    cc('title').value = preset.job_title;
    document.querySelectorAll('#cc-good input, #cc-bad input').forEach(box => {
        box.checked = preset.traits.includes(box.value);
    });
    refreshCreation();
    refreshOutfit(preset.outfit);
}

function traitBoxes(container, traits) {
    container.innerHTML = '';
    traits.forEach(trait => {
        const label = el('label', 'trait-option');
        const box = document.createElement('input');
        box.type = 'checkbox';
        box.value = trait.id;
        box.addEventListener('change', refreshCreation);
        label.appendChild(box);
        label.appendChild(el('span', 'name', trait.name));
        label.appendChild(el('span', 'cost', String(Math.abs(trait.cost))));
        label.appendChild(el('span', 'desc', trait.description));
        container.appendChild(label);
    });
}

async function openCreation() {
    if (!creationData) {
        const response = await fetch('/creation');
        creationData = await response.json();
        const looks = creationData.appearance;
        fillSelect(cc('gender'), looks.genders.map(g => [g, capitalised(g)]));
        fillSelect(cc('skin'), Object.entries(looks.skin_tones).map(([v, name]) => [v, capitalised(name)]));
        fillSelect(cc('hair-style'), looks.hair_styles.map(h => [h, capitalised(h)]));
        fillSelect(cc('hair-colour'), looks.hair_colours.map(h => [h, capitalised(h)]));
        fillSelect(cc('beard'), looks.beard_styles.map(b => [b, b ? capitalised(b) : 'None']));
        fillSelect(cc('occupation'), creationData.occupations.map(o => [o.id, `${o.name} (${o.cost > 0 ? '+' : ''}${o.cost})`]));
        fillSelect(cc('preset'), [['', 'Build your own'], ...Object.keys(creationData.presets).map(id => [id, capitalised(id)])]);
        traitBoxes(cc('good'), creationData.traits.good);
        traitBoxes(cc('bad'), creationData.traits.bad);
        cc('occupation').addEventListener('change', () => { dropClashingTraits(); refreshCreation(); });
        cc('gender').addEventListener('change', refreshCreation);
        cc('preset').addEventListener('change', () => {
            if (cc('preset').value) fillFromPreset(creationData.presets[cc('preset').value]);
        });
        refreshCreation();
    }
    creationScreen.hidden = false;
}

document.getElementById('creation-form').addEventListener('submit', async event => {
    event.preventDefault();
    const errors = document.getElementById('creation-errors');
    errors.innerHTML = '';
    const response = await fetch('/creation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildFromForm()),
    });
    const data = await response.json();
    if (!response.ok) {
        (data.errors || ['Could not start the game.']).forEach(message => {
            const item = document.createElement('li');
            item.textContent = message;
            errors.appendChild(item);
        });
        return;
    }
    creationScreen.hidden = true;
    storyDisplay.innerHTML = '';
    appendStory(null, 'The adventure begins.');
    updatePanel(data);
});

// Event listeners
inputForm.addEventListener('submit', handleTurn);
resetButton.addEventListener('click', handleReset);
saveButton.addEventListener('click', handleSave);
loadButton.addEventListener('click', handleLoad);
loadInput.addEventListener('change', handleLoadFile);

buildTabs();
loadState();
playerInput.focus();
