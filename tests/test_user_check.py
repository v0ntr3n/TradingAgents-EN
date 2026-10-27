"""Check user database"""
from pymongo import MongoClient

# Direct connection MongoDB
mongo_uri = "mongodb://admin:tradingagents123@localhost:27017/"
client = MongoClient(mongo_uri)

print(f"🔍 MongoDB URI: {mongo_uri}")
print()

# List all databases
print("📊 All databases:")
for db_name in client.list_database_names():
    print(f"  - {db_name}")
print()

# Check two possible databases
for db_name in ["tradingagents"]:
    print(f"=" * 60)
    print(f"🔍 Check database: {db_name}")
    print(f"=" * 60)

    db = client[db_name]

    # list all collections
    collections = db.list_collection_names()
    print(f"📁 Collection list: {collections}")
    print()

    if "users" in collections:
        # Query all users
        users = list(db.users.find({}))
        print(f"📊 found {len(users)} users:")
        print()

        for user in users:
            print(f"Username: {user.get('username')}")
            print(f"  - ID: {user.get('_id')}")
            print(f"  - Email: {user.get('email')}")
            print(f"  - active state: {user.get('is_active')}")
            print(f"  - Administrator: {user.get('is_admin')}")
            print(f"  - Password hash: {user.get('hashed_password', '')[:20]}...")
            print()

        # Test query admin user
        print("🔍 Test query admin user:")
        admin_user = db.users.find_one({"username": "admin"})
        if admin_user:
            print(f"✅ Find the admin user:")
            print(f"  - ID: {admin_user.get('_id')}")
            print(f"  - Email: {admin_user.get('email')}")
            print(f"  - active state: {admin_user.get('is_active')}")
        else:
            print("❌ admin user not found")
    else:
        print("⚠️ There is no users collection")

    print()

client.close()

