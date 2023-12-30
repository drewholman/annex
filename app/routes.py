from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.urls import url_parse
from flask_babel import _, get_locale
from app import app, db
from app.forms import LoginForm, RegistrationForm, EditProfileForm, \
    EmptyForm, PostForm, ResetPasswordRequestForm, ResetPasswordForm
from app.models import User, Post
from app.email import send_password_reset_email
import json
from app.models import Item, Account, Transaction
import plaid
from app.cash.plaid_connect import authorize_and_create_transfer, get_institution, pretty_print_response, format_error, configure, get_products, check_institution, get_institution
from sqlalchemy import and_
from plaid.model.country_code import CountryCode
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.api import plaid_api


@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
    g.locale = str(get_locale())


@app.route('/', methods=['GET', 'POST'])
@app.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    form = PostForm()
    if form.validate_on_submit():
        post = Post(body=form.post.data, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash(_('Your post is now live!'))
        return redirect(url_for('index'))
    page = request.args.get('page', 1, type=int)
    posts = current_user.followed_posts().paginate(
        page=page, per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('index', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('index', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('Home'), form=form,
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


@app.route('/explore')
@login_required
def explore():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('explore', page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('explore', page=posts.prev_num) \
        if posts.has_prev else None
    return render_template('index.html', title=_('Explore'),
                           posts=posts.items, next_url=next_url,
                           prev_url=prev_url)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash(_('Invalid username or password'))
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title=_('Sign In'), form=form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(_('Congratulations, you are now a registered user!'))
        return redirect(url_for('login'))
    return render_template('register.html', title=_('Register'), form=form)


@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash(
            _('Check your email for the instructions to reset your password'))
        return redirect(url_for('login'))
    return render_template('reset_password_request.html',
                           title=_('Reset Password'), form=form)


@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(_('Your password has been reset.'))
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)


@app.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(
        page=page, per_page=app.config['POSTS_PER_PAGE'], error_out=False)
    next_url = url_for('user', username=user.username, page=posts.next_num) \
        if posts.has_next else None
    prev_url = url_for('user', username=user.username, page=posts.prev_num) \
        if posts.has_prev else None
    form = EmptyForm()
    return render_template('user.html', user=user, posts=posts.items,
                           next_url=next_url, prev_url=prev_url, form=form)


@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Your changes have been saved.'))
        return redirect(url_for('edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title=_('Edit Profile'),
                           form=form)


@app.route('/follow/<username>', methods=['POST'])
@login_required
def follow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('index'))
        if user == current_user:
            flash(_('You cannot follow yourself!'))
            return redirect(url_for('user', username=username))
        current_user.follow(user)
        db.session.commit()
        flash(_('You are following %(username)s!', username=username))
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))


@app.route('/unfollow/<username>', methods=['POST'])
@login_required
def unfollow(username):
    form = EmptyForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=username).first()
        if user is None:
            flash(_('User %(username)s not found.', username=username))
            return redirect(url_for('index'))
        if user == current_user:
            flash(_('You cannot unfollow yourself!'))
            return redirect(url_for('user', username=username))
        current_user.unfollow(user)
        db.session.commit()
        flash(_('You are not following %(username)s.', username=username))
        return redirect(url_for('user', username=username))
    else:
        return redirect(url_for('index'))

access_token = None

## Get transactions by group
@bp.route('/transactions/<group_id>', methods=['GET'])
def get_transactions(group_id):
    group = Group.query.filter_by(id=group_id)
    return render_template('cash/transactions.html', title="Test", group=group)

## Update transaction metadata
@bp.route('/transaction/update', methods=['POST'])
def update_transaction():
    print(request.json)
    ## Query old and new name matches for first time updates or a new_name switch
    transactions = Transaction.query.filter( (Transaction.original_name.like(request.json['old_name'])) |
        (Transaction.new_name.like(request.json['old_name'])) ).all()
    ##TODO: Update all transactions with a similar name
    for t in transactions:
        t.new_name = request.json['new_name']
        print(t.original_name)
    db.session.commit()
    return redirect(url_for('cash.dashboard'))

## Dedupe linked institutions
@bp.route('/user/institution/<ins_id>', methods=['GET'])
def dedupe_instution(ins_id):
    if check_institution(ins_id) == "exists":
        flash(_('Institution has already been linked, "Refresh" instead'))
    return jsonify(check_institution(ins_id))

## Return oauth route for oauth banks
@bp.route('/oauth', methods=['GET'])
def oauth():
    return render_template('cash/oauth.html', title=_('OAuth'))

## Create link token for Plaid Link
@bp.route('/create_link_token', methods=['POST', 'GET'])
def create_link_token():
    client = configure()
    products = get_products()

    try:
        request = LinkTokenCreateRequest(
            products=products,
            client_name="Anex Connect",
            country_codes=list(map(lambda x: CountryCode(x), current_app.config['PLAID_COUNTRY_CODES'])),
            language='en',
            webhook='http://e9dd-67-185-58-96.ngrok.io/cash/event',
            # webhook='https://coda.io/apis/v1/docs/w0-kg2eEuP/hooks/automation/grid-auto-5Hnjl4QPh5',
            user=LinkTokenCreateRequestUser(
                client_user_id=str(time.time())
            )
        )
        if current_app.config['PLAID_REDIRECT_URI']!=None:
            request['redirect_uri']=current_app.config['PLAID_REDIRECT_URI']
    # create link token
        response = client.link_token_create(request)
        return jsonify(response.to_dict())
    except plaid.ApiException as e:
        return json.loads(e.body)

## Webhook to check for new transactions. Check logs here: https://dashboard.plaid.com/activity/logs?environment=ENV_SANDBOX&timezone=America%2FLos_Angeles 
@bp.route('/event', methods=['POST'])
def event():
    print(request.json)
    webhook_code = request.json['webhook_code']
    if webhook_code == "SYNC_UPDATES_AVAILABLE" or webhook_code == "TRANSACTIONS_REMOVED" or webhook_code == "DEFAULT_UPDATE":
        item_id = request.json['item_id']
        # Fire the transaction endpoint and get new data
        sync_transactions(item_id)
        # Update balances for accounts within the item
        # update_balance(item_id)/Applications/Visual Studio Code.app/Contents/Resources/app/out/vs/code/electron-browser/workbench/workbench.html
    return {'success': True}

## TODO: Handle item expiration and new account adds (i.e. ITEM_LOGIN_REQUIRED)
## Update mode: https://plaid.com/docs/link/update-mode/
## Item json schema here:https://plaid.com/docs/api/items/#webhooks
## https://plaid.com/docs/api/items/#error
## Item handling example here: https://github.com/plaid/pattern/blob/master/server/webhookHandlers/handleItemWebhook.js
@bp.route('/item/event', methods=['POST'])
def item_event():
    print(request.json)
    webhook_code = request.json['webhook_code']
    if webhook_code == "ITEM_LOGIN_REQUIRED" or webhook_code == "PENDING_EXPIRATION":
        print('item update notification')
    elif webhook_code == "NEW_ACCOUNTS_AVAILABLE":
        print('notify to add new accounts')
    return {'success': True}

## Set item access token in Plaid Link process
@bp.route('/set_access_token', methods=['POST'])
def set_access_token():
    client = configure()

    global access_token
    global item_id
    global transfer_id

    public_token = request.get_json()['public_token']
    try:
        exchange_request = ItemPublicTokenExchangeRequest(
            public_token=public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response['access_token']
        item_id = exchange_response['item_id']
        #pretty_print_response(exchange_response.to_dict())
        if 'transfer' in current_app.config['PLAID_PRODUCTS']:
            transfer_id = authorize_and_create_transfer(access_token)
        return jsonify(exchange_response.to_dict())
    except plaid.ApiException as e:
        return json.loads(e.body)

## Update current balances for an item
@bp.route('/balance/<item_id>/update', methods=['GET'])
def update_balance(item_id):
    access_token = Item.query.filter_by(id=item_id).first().access_token
    client = configure()

    try:
        request = AccountsBalanceGetRequest(
            access_token=access_token
        )
        response = client.accounts_balance_get(request)
        accounts = response['accounts']
        for a in accounts:
            id = a['account_id']
            balance = a['balances']['current']
            account = Account.query.filter_by(id=id).first()
            account.current_balance = balance
            db.session.commit()
        return jsonify(response.to_dict()) 
    except plaid.ApiException as e:
        error_response = format_error(e)
        return jsonify(error_response)
    
## Get balances & add new item & accounts to db
@bp.route('/balance/get', methods=['GET'])
def get_balance():
    client = configure()

    try:
        request = AccountsBalanceGetRequest(
            access_token=access_token
        )
        response = client.accounts_balance_get(request)
        ins_id = response['item']['institution_id']
        ins_name = get_institution(ins_id)
        item = Item(id=response['item']['item_id'], access_token=access_token, owner=current_user, ins_id=ins_id, ins_name=ins_name)
        db.session.add(item)
        db.session.commit()
        group = Group.query.filter(Group.user_id==item.user_id, Group.name.like("Uncategorized")).first()
        accounts = response['accounts']
        for a in accounts:
            id = a['account_id']
            name = a['name']
            item = response['item']['item_id']
            balance = a['balances']['current']
            account_type = str(a['subtype'])
            account = Account(id=id, name=name, item_id=item, current_balance=balance, type=account_type, group_id=group.id)
            db.session.add(account)
            db.session.commit()
        return jsonify(response.to_dict())
    except plaid.ApiException as e:
        error_response = format_error(e)
        return jsonify(error_response)

## Get institution name for db storage
@bp.route('/institution/<ins_id>', methods=['GET'])
def institution(ins_id):
    client = configure()

    try:
        request = InstitutionsGetByIdRequest(
            institution_id=ins_id,
            country_codes=list(map(lambda x: CountryCode(x), current_app.config['PLAID_COUNTRY_CODES'])),
        )
        response = client.institutions_get_by_id(request)
        print(response['institution']['name'])
        return jsonify(response.to_dict())

    except plaid.ApiException as e:
        error_response = format_error(e)
        return jsonify(error_response)

## Remove item, associated accounts & transactions from the db
@bp.route('/item/<item_id>/delete')
def delete_item(item_id):
    client = configure()
    item = Item.query.filter_by(id=item_id).first()

    try:
        request = ItemRemoveRequest(access_token=item.access_token)
        response = client.item_remove(request)
        ## Remove associated Accounts
        accounts = Account.query.filter_by(item_id=item.id)
        account_list = []
        for a in accounts:
            account_list.append(a.id)
        account_list = tuple(account_list)
        ## Remove associated Transactions
        transactions = db.session.query(Transaction).filter(Transaction.account_id.in_(account_list))
        accounts.delete()
        transactions.delete()
        db.session.delete(item)
        db.session.commit()
        return jsonify(response.to_dict())
    except plaid.ApiException as e:
        error_response = format_error(e)
        return jsonify(error_response)

## Sync transactions after webhook event
@bp.route('/item/<item_id>/transactions', methods=['GET'])
def sync_transactions(item_id):
    print(item_id)
    client = configure()
    item = Item.query.filter_by(id=item_id).first()
    access_token = item.access_token

    # New transaction updates since "cursor"
    added = []
    modified = []
    removed = [] # Removed transaction ids
    has_more = True

    try:
        # Iterate through each page of new transaction updates for item
        while has_more:
            cursor = Item.get_latest_cursor_or_none(item_id)
            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor=cursor,
            )
            response = client.transactions_sync(request).to_dict()
            # Add this page of results
            added.extend(response['added'])
            modified.extend(response['modified'])
            removed.extend(response['removed'])
            has_more = response['has_more']
            # Update cursor to the next cursor
            cursor = response['next_cursor']
            item.cursor = cursor
            db.session.commit()

        Transaction.handle_db_transactions(added, modified, removed, current_user) 
        return jsonify({'added': added})
        
    except plaid.ApiException as e:
        error_response = e
        return jsonify(error_response)

## TODO: https for oauth

## TODO: Account select v2 webhook & reconcile with item de-duplication https://plaid.com/docs/link/account-select-v2-migration-guide/

## TODO: Update balances on a regular basis
## TODO: Update items instead of re-adding when they break or get disconnected https://plaid.com/docs/link/update-mode/

## TODO: Flow: First time, get balances & add accounts and items to the db
## TODO: Second time, just get balances

## TODO: Set currency locale https://stackoverflow.com/questions/320929/currency-formatting-in-python

## TODO: Research @loginrequired, is it needed for cashflow access