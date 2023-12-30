from datetime import datetime
from hashlib import md5
from time import time
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from app import app, db, login


followers = db.Table(
    'followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    about_me = db.Column(db.String(140))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
            digest, size)

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

    def followed_posts(self):
        followed = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter(
                followers.c.follower_id == self.id)
        own = Post.query.filter_by(user_id=self.id)
        return followed.union(own).order_by(Post.timestamp.desc())

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    def __repr__(self):
        return '<Post {}>'.format(self.body)

class Item(db.Model):
    id = db.Column(db.String(60), primary_key=True)
    access_token = db.Column(db.String(60), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    ins_id = db.Column(db.String(10))
    ins_name = db.Column(db.String(120))
    cursor = db.Column(db.String(120))

    def __repr__(self):
        return '<Item {}>'.format(self.ins_name)

    def get_latest_cursor_or_none(item_id):
        item = Item.query.filter_by(id=item_id).first()
        if item.cursor == None:
            cursor = ""
        else:
            cursor = item.cursor
        return cursor

class Account(db.Model):
    id = db.Column(db.String(60), primary_key=True)
    name = db.Column(db.String(128), index=True)
    item_id = db.Column(db.String(60), db.ForeignKey('item.id'))
    current_balance = db.Column(db.Float)
    type = db.Column(db.String(20))
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'))

    def __repr__(self):
        return '<Account {}>'.format(self.name)
class Transaction(db.Model):
    id = db.Column(db.String(60), primary_key=True)
    original_name = db.Column(db.String(140))
    new_name = db.Column(db.String(140))
    account_id = db.Column(db.String(60), db.ForeignKey('account.id'))
    date = db.Column(db.DateTime)
    vendor_name = db.Column(db.String(140))
    vendor_type = db.Column(db.String(32))
    amount = db.Column(db.Float)
    iso_currency_code = db.Column(db.String(10))
    transaction_type = db.Column(db.String(20))
    category_name = db.Column(db.String(128))
    category_id = db.Column(db.Integer)

    def __repr__(self):
        return '<Transaction {}>'.format(self.vendor_name)

    def month_day(self):
        return "{:s} {:02d}".format(self.date.strftime("%b"), self.date.day)

    def handle_db_transactions(added, modified, removed, current_user):
        count = 0
        if added != []:
            for a in added:
                count +=1
                ## Check if this particular transaction has been renamed by the user
                name_check = db.session.query(Transaction).join(
                    Account).join(
                        Item).filter(
                            and_(Item.user_id == current_user.id, Transaction.original_name.like(a['name']))).first()
                if name_check != None:
                    new_name = name_check.new_name
                else:
                    new_name = None
                date = None if str(a['date']) == "None" else datetime.strptime(str(a['date']), "%Y-%m-%d")
                transaction = Transaction(id=a['transaction_id'], original_name=a['name'], new_name=new_name,
                                account_id=a['account_id'], 
                                date=date, vendor_name=a['merchant_name'], 
                                amount=a['amount'], iso_currency_code=a['iso_currency_code'],
                                transaction_type=a['payment_channel'], category_name=a['category'][0], category_id=a['category_id'])
                db.session.add(transaction)
        print(str(count) +" Transactions added")

        if modified != []:   
            for m in modified:
                transaction = Transaction.query.filter_by(id=m['transaction_id']).first()
                transaction.original_name = m['name']
                transaction.account_id = m['account_id']
                transaction.datetime = None if str(m['date']) == "None" else datetime.strptime(str(m['date']), "%Y-%m-%d")
                transaction.vendor_name = m['merchant_name']
                transaction.amount = m['amount']
                transaction.currency_code = m['iso_currency_code']
                transaction.transaction_type = m['payment_channel']
                transaction.category_name = m['category'][0]
                transaction.category_id = m['category_id']
        
        if removed != []:
            for r in removed:
                transaction = Transaction.query.filter_by(id=r['transaction_id']).first()
                db.session.delete(transaction)

        db.session.commit()

    def transactions(accounts):
        ## Create an WHERE account_id=(this OR this OR)
        account_list = []
        for a in accounts:
            account_list.append(a.id)  
        transactions = Transaction.query.filter(Transaction.account_id.in_(account_list)).all()
        return transactions