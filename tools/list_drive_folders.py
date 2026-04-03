from video_search import get_drive_service

def list_folders():
    service = get_drive_service()
    results = service.files().list(
        q="mimeType='application/vnd.google-apps.folder'",
        fields="nextPageToken, files(id, name)"
    ).execute()
    folders = results.get('files', [])
    
    if not folders:
        print('No folders found.')
    else:
        print('Folders Found:')
        for folder in folders:
            print(f"{folder['name']} (ID: {folder['id']})")

if __name__ == '__main__':
    list_folders()
