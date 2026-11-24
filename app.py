import os
import hmac
import streamlit as st
from voting import Store, ElectionError, N, make_code

st.set_page_config(page_title='Community Election', page_icon='🗳️', layout='centered')

def config_value(key):
    return os.environ.get(key) or st.secrets.get(key, '')


def get_store():
    url = config_value('DATABASE_URL')
    if not url:
        raise ElectionError('Database connection is not configured. Contact the organizer.')
    return Store(url)


def valid_setup_code(code):
    expected = config_value('SETUP_PASSWORD')
    return isinstance(expected, str) and len(expected) >= 24 and hmac.compare_digest(
        code.encode('utf-8'), expected.encode('utf-8'))


def setup_page(store):
    st.subheader('One-time election setup')
    st.caption('Only the organizer with the private setup password may initialize this election.')
    if not valid_setup_code(st.session_state.get('setup_auth', '')):
        with st.form('setup_login', clear_on_submit=True):
            password = st.text_input('Setup password', type='password', max_chars=256)
            unlock = st.form_submit_button('Unlock setup')
        if unlock:
            if valid_setup_code(password):
                st.session_state['setup_auth'] = password
                st.rerun()
            else:
                st.error('Invalid setup password.')
        return
    if st.button('Sign out of setup'):
        logout()
    if 'draft' not in st.session_state:
        with st.form('roster'):
            raw_members = st.text_area('13 voter / candidate names (one per line)', height=300)
            raw_admins = st.text_area('3 administrator names (one per line)', height=120)
            generate = st.form_submit_button('Generate private access codes')
        if generate:
            names = [x.strip() for x in raw_members.splitlines() if x.strip()]
            admins = [x.strip() for x in raw_admins.splitlines() if x.strip()]
            if len(names) != N or len({n.casefold() for n in names}) != N or len(admins) != 3 or len({n.casefold() for n in admins}) != 3:
                st.error('Enter exactly 13 distinct member names and 3 distinct administrator names.')
                return
            st.session_state['draft'] = (names, admins, [make_code() for _ in names], [make_code() for _ in admins])
            st.rerun()
        return
    names, admins, voter_codes, admin_codes = st.session_state['draft']
    st.warning('Download and keep these codes privately BEFORE initializing. They cannot be recovered from the database. Send each person only their own code.')
    records = ['PRIVATE — member access codes'] + [f'{n}: {c}' for n,c in zip(names,voter_codes)] + ['','PRIVATE — administrator access codes'] + [f'{n}: {c}' for n,c in zip(admins,admin_codes)]
    st.download_button('Download private access codes', '\n'.join(records)+'\n', file_name='private_access_codes.txt', mime='text/plain')
    st.write('Members: ' + ', '.join(names))
    st.write('Administrators: ' + ', '.join(admins))
    saved = st.checkbox('I saved the private access codes and agree that initialization cannot be undone.')
    if st.button('Initialize election', type='primary', disabled=not saved):
        if not valid_setup_code(st.session_state.get('setup_auth', '')):
            raise ElectionError('Setup authorization expired.')
        store.setup(names, admins, voter_codes, admin_codes)
        st.session_state.clear()
        st.session_state['setup_complete'] = True
        st.rerun()
    if st.button('Change roster / regenerate codes'):
        st.session_state.pop('draft', None)
        st.rerun()


def logout():
    st.session_state.clear()
    st.rerun()


def rules():
    with st.expander('Election rules & privacy'):
        st.write('Rank the 12 other members. First choice receives 12 points, second 11, and last 1. '
                 'Every member submits one final ballot. No self-voting or repeated candidates. '
                 'Equal totals are resolved by comparing first-choice counts, then second-choice counts, '
                 'and so on. Identical preference counts are resolved by the priority order fixed at setup.')
        st.warning('Your ballot is confidential from other voters, not anonymous to the three authorized administrators. '
                   'They can inspect identity-linked ballots after the election ends. The hosting/database owner also has technical access. '
                   'Do not share your private access code.')


def show_results(store, role, code):
    results = store.results(role, code)
    st.success('Election complete — all 13 ballots received.')
    a, b = st.columns(2)
    a.metric('Position 1', results[0]['name'], f"{results[0]['points']} points", delta_color='off')
    b.metric('Position 2', results[1]['name'], f"{results[1]['points']} points", delta_color='off')
    st.subheader('Final ranking')
    st.dataframe([{'Position': r['position'], 'Member': r['name'], 'Points': r['points'],
                   'First choices': r['counts'][0]} for r in results], hide_index=True, use_container_width=True)
    st.caption('Equal points are not necessarily equal ranks; the published tie-breaking rules apply.')
    if role == 'admin':
        st.subheader('Private administrator audit')
        st.warning('Contains voter identities and preferences. Do not share with ordinary members.')
        with st.expander('Who voted for whom — ordered ballot table'):
            st.dataframe([{'Voter': voter, **{f'#{i+1} ({N-1-i} pt)': candidate for i, candidate in enumerate(ranking)}}
                          for voter, ranking in store.audit(code)], hide_index=True, use_container_width=True)
        with st.expander('Full tie-break statistics'):
            st.dataframe([{'Position': r['position'], 'Member': r['name'], 'Points': r['points'],
                           **{f'Choice {i+1}': n for i, n in enumerate(r['counts'])}, 'Fixed priority': r['priority']}
                          for r in results], hide_index=True, use_container_width=True)


def main():
    st.title('Community Election')
    st.caption('13 members · 13 unique positions · one confidential ballot per member')
    store = get_store()
    if not store.initialized():
        setup_page(store)
        return
    st.session_state.pop('draft', None)
    st.session_state.pop('setup_auth', None)
    if st.session_state.pop('setup_complete', False):
        st.success('Election initialized. Sign in with your administrator or member code. Share the fixed tie-break priority before voting begins.')
    if 'auth' not in st.session_state:
        rules()
        with st.form('login', clear_on_submit=True):
            role_label = st.radio('Access type', ['Member voting', 'Administrator'], horizontal=True)
            code = st.text_input('Private access code', type='password', max_chars=256)
            go = st.form_submit_button('Sign in', type='primary', use_container_width=True)
        if go:
            role = 'member' if role_label == 'Member voting' else 'admin'
            try:
                store.login(role, code)
            except ElectionError as e:
                st.error(str(e))
                return
            st.session_state['auth'] = (role, code.strip())
            st.rerun()
        return
    role, code = st.session_state['auth']
    info = store.overview(role, code)
    left, right = st.columns([3, 1])
    left.write(f"Signed in as **{info['name']}** ({'administrator' if role == 'admin' else 'member'})")
    if right.button('Sign out'):
        logout()
    st.progress(info['count'] / N, text=f"{info['count']} of {N} ballots received")
    rules()
    with st.expander('Fixed final tie-break order (set before voting)'):
        st.write('This priority is used only when all preference-count statistics are identical.')
        st.table([{'Priority': i+1, 'Member': name} for i, name in enumerate(info['priority'])])
    if info['count'] == N:
        show_results(store, role, code)
        return
    if role == 'admin':
        st.info('Individual ballots and interim scores are locked until everyone votes. '
                'If you are also a candidate, sign out and use your separate member code to vote.')
        st.button('Refresh election status')
        return
    if info['submitted']:
        st.success('Your ballot is safely recorded. You cannot vote again or change it.')
        st.info('Return after all 13 members have voted to see the final ranking.')
        st.button('Refresh election status')
        return
    st.subheader('Rank your 12 fellow members')
    st.write('Select a different person for each rank. The strongest preference goes first.')
    candidates = [i for i, name in sorted(info['roster'].items(), key=lambda t: t[1].casefold()) if i != info['id']]
    with st.form('ballot'):
        ranking = [st.selectbox(f'Choice {j+1} — {N-1-j} points', candidates, index=None,
                                placeholder='Select a member', format_func=lambda i: info['roster'][i],
                                key=f'choice_{j}') for j in range(N-1)]
        confirmed = st.checkbox('I have checked my ranking and understand my ballot cannot be changed.')
        submit = st.form_submit_button('Submit final ballot', type='primary', use_container_width=True)
    if submit:
        if not confirmed:
            st.error('Confirm your ballot before submitting.')
        elif None in ranking or len(set(ranking)) != N-1:
            st.error('Choose all 12 different members exactly once. No ballot has been recorded.')
        else:
            try:
                store.submit(code, ranking)
            except ElectionError as e:
                st.error(str(e))
            else:
                st.rerun()


try:
    main()
except ElectionError as e:
    st.error(str(e))
    if 'auth' in st.session_state and st.button('Sign out and retry'):
        logout()
except Exception:
    # Avoid showing database URLs, credentials or stack traces to visitors.
    st.error('The election database is unavailable or not initialized. Contact an administrator.')
