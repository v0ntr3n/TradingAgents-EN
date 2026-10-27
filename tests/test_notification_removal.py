#!/usr/bin/env python3
"""
Verification notification feature removed
Check whether there is any notification-related code in the front-end code
"""
import os
import re

def check_notification_code():
    """Check the notification-related code in the front-end code"""
    print("=" * 60)
    print("🔍 Check notification removal status")
    print("=" * 60)
    
    frontend_dir = "frontend/src"
    notification_patterns = [
        r'showDesktopNotification',
        r'testNotification',
        r'Test notification',
        r'Notification\.permission',
        r'new Notification',
        r'requestPermission',
        r'🧪 Test notification'
    ]
    
    found_issues = []
    
    # Traverse front-end files
    for root, dirs, files in os.walk(frontend_dir):
        for file in files:
            if file.endswith(('.vue', '.ts', '.js')):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Check each pattern
                    for pattern in notification_patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            # Calculate line number
                            line_num = content[:match.start()].count('\n') + 1
                            line_content = content.split('\n')[line_num - 1].strip()
                            
                            found_issues.append({
                                'file': file_path,
                                'line': line_num,
                                'pattern': pattern,
                                'content': line_content
                            })
                            
                except Exception as e:
                    print(f"⚠️ Unable to read file {file_path}: {e}")
    
    # Report results
    if found_issues:
        print(f"❌ discover {len(found_issues)} Notification related code residue:")
        print()
        
        for issue in found_issues:
            print(f"📁 File: {issue['file']}")
            print(f"📍 Line number: {issue['line']}")
            print(f"🔍 mode: {issue['pattern']}")
            print(f"📝 content: {issue['content']}")
            print("-" * 40)
            
        return False
    else:
        print("✅ No notification related code residue found")
        return True

def check_sync_control_component():
    """Specifically check the SyncControl component"""
    print("\n" + "=" * 60)
    print("🔍 Check the SyncControl component")
    print("=" * 60)
    
    sync_control_path = "frontend/src/components/Sync/SyncControl.vue"
    
    if not os.path.exists(sync_control_path):
        print(f"❌ File does not exist: {sync_control_path}")
        return False
    
    try:
        with open(sync_control_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for features that should be removed
        removed_features = [
            '🧪 Test notification',
            'testNotification',
            'showDesktopNotification',
            'Notification.permission',
            'new Notification'
        ]
        
        # Check for features that should be retained
        kept_features = [
            'showSyncCompletionNotification',
            'ElMessage',
            'emit(\'syncCompleted\'',
        ]
        
        print("📋 Check for removed features:")
        all_removed = True
        for feature in removed_features:
            if feature in content:
                print(f"   ❌ still exists: {feature}")
                all_removed = False
            else:
                print(f"   ✅ Removed: {feature}")
        
        print("\n📋 Check reserved features:")
        all_kept = True
        for feature in kept_features:
            if feature in content:
                print(f"   ✅ Reserved: {feature}")
            else:
                print(f"   ❌ Accidental removal: {feature}")
                all_kept = False
        
        # Check number of buttons
        button_count = content.count('<el-button')
        print(f"\n📊 Number of buttons: {button_count}")
        
        # There should be 4 buttons: start synchronization, refresh status, clear cache, force resynchronization
        expected_buttons = 4
        if button_count == expected_buttons:
            print(f"   ✅ Correct number of buttons (Expectation: {expected_buttons})")
        else:
            print(f"   ⚠️ The number of buttons may be incorrect (Expectation: {expected_buttons}, actual: {button_count})")
        
        return all_removed and all_kept
        
    except Exception as e:
        print(f"❌ Failed to read file: {e}")
        return False

def generate_test_instructions():
    """Generate test instructions"""
    print("\n" + "=" * 60)
    print("📝 Front-end testing instructions")
    print("=" * 60)
    
    print("Now you can verify the following functionality on the frontend:")
    print()
    print("✅ **Features that should work properly:**")
    print("   1. 🚀 Start sync button")
    print("   2. 🔄 refresh status button")
    print("   3. 🗑️ Clear cache button")
    print("   4. 💪 Force resync button")
    print("   5. 📊 Sync status display")
    print("   6. 📈 Sync statistics")
    print("   7. 💬 Page message prompt (ElMessage)")
    print("   8. 📚 Sync history")
    print()
    print("❌ **Features that should have been removed:**")
    print("   1. 🧪 Test notification button")
    print("   2. 🔔 Desktop notifications")
    print("   3. 📱 Notify permission request")
    print()
    print("🧪 **Test steps:**")
    print("   1. Open the multi-data source synchronization page")
    print("   2. Confirm that there are only 4 action buttons")
    print("   3. Click'force resync'")
    print("   4. Observe whether only page messages are displayed and no desktop notifications are displayed")
    print("   5. Check whether the synchronization history is updated normally")
    print()
    print("If all the above tests pass, it means that the notification function has been removed successfully!")

if __name__ == "__main__":
    print("🧹 Notification feature removal verification")
    
    # Check code residue
    code_clean = check_notification_code()
    
    # Check components
    component_clean = check_sync_control_component()
    
    # Generate test instructions
    generate_test_instructions()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Verification results")
    print("=" * 60)
    
    if code_clean and component_clean:
        print("🎉 Notification function removed successfully!")
        print("   ✅ Code cleanup completed")
        print("   ✅ Component functions correctly")
        print("   📝 Please follow the instructions above for front-end testing")
    else:
        print("⚠️ A problem is found and further inspection is required:")
        if not code_clean:
            print("   ❌ There are still notification related residues in the code")
        if not component_clean:
            print("   ❌ Component functionality is incorrect")
