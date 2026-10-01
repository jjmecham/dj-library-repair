$root = "C:\Users\Jeremy\Music"

function Show-GhostFolders {
    Write-Host "`n=== Ghost Folders (Appear Empty but Contain Hidden/System Files) ===`n"
    Get-ChildItem -Directory -Recurse $root |
    Where-Object {
        (Get-ChildItem $_.FullName -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0 -and
        (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0
    } |
    Select-Object FullName
}

function Fix-GhostFolders {
    Write-Host "`n=== Fixing Ghost Folders ===`n"

    $ghosts = Get-ChildItem -Directory -Recurse $root |
    Where-Object {
        (Get-ChildItem $_.FullName -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0 -and
        (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0
    }

    foreach ($folder in $ghosts) {
        Write-Host "Processing: $($folder.FullName)"

        # Reveal hidden/system files by removing attributes
        Get-ChildItem $folder.FullName -Force -ErrorAction SilentlyContinue |
        ForEach-Object {
            attrib -h -s $_.FullName
        }

        # Remove common junk files
        $junk = @("desktop.ini", "thumbs.db")
        foreach ($j in $junk) {
            $junkPath = Join-Path $folder.FullName $j
            if (Test-Path $junkPath) {
                Write-Host "Removing junk file: $junkPath"
                Remove-Item $junkPath -Force
            }
        }

        # If folder is now empty, delete it
        if ((Get-ChildItem $folder.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0) {
            Write-Host "Deleting empty folder: $($folder.FullName)"
            Remove-Item $folder.FullName -Force
        }
    }

    Write-Host "`nGhost folder cleanup complete.`n"
}

function Show-EmptyFolders {
    Write-Host "`n=== Truly Empty Folders (Safe to Delete) ===`n"
    Get-ChildItem -Directory -Recurse $root |
    Where-Object {
        (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0
    } |
    Select-Object FullName
}

function Delete-EmptyFolders {
    Write-Host "`n=== Deleting Truly Empty Folders ===`n"
    Get-ChildItem -Directory -Recurse $root |
    Sort-Object FullName -Descending |
    Where-Object {
        (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue | Measure-Object).Count -eq 0
    } |
    ForEach-Object {
        Write-Host "Deleting: $($_.FullName)"
        Remove-Item $_.FullName -Force
    }
    Write-Host "`nDone.`n"
}

while ($true) {
    Write-Host "==============================="
    Write-Host "   Music Folder Maintenance"
    Write-Host "==============================="
    Write-Host "1. Show ghost folders"
    Write-Host "2. Fix ghost folders"
    Write-Host "3. Show truly empty folders"
    Write-Host "4. Delete truly empty folders"
    Write-Host "5. Exit"
    Write-Host "==============================="
    $choice = Read-Host "Choose an option"

    switch ($choice) {
        "1" { Show-GhostFolders }
        "2" { Fix-GhostFolders }
        "3" { Show-EmptyFolders }
        "4" { Delete-EmptyFolders }
        "5" { break }
        default { Write-Host "Invalid selection. Try again." }
    }
}
