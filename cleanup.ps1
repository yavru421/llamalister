# Create archive directories
New-Item -ItemType Directory -Path archive -Force
New-Item -ItemType Directory -Path archive\llamalister -Force
New-Item -ItemType Directory -Path archive\Core_AUA_System -Force
New-Item -ItemType Directory -Path archive\Core_AUA_System\src -Force
New-Item -ItemType Directory -Path archive\Core_AUA_System\src\agents -Force
New-Item -ItemType Directory -Path archive\Core_AUA_System\src\agents\operations -Force
New-Item -ItemType Directory -Path archive\Core_AUA_System\src\core -Force

# Move files
Move-Item build_llamalister_legacy.ps1 archive\
Move-Item llamalister_legacy.py archive\
Move-Item LlamaLister_legacy.spec archive\
Move-Item LlamaLister.pkg archive\
Move-Item warn-LlamaLister.txt archive\
Move-Item xref-LlamaLister.html archive\
Move-Item llamalister.py archive\
Move-Item build_llamalister.py archive\
Move-Item README.txt archive\

# Move data and cache files
Move-Item .\llamalister\Hand-Quilted_Wolf_Portrait_Quilt_-_Wildlife_Art_for_the_Home.csv archive\llamalister\
Move-Item .\llamalister\Unique_Spine_Lamp_A_Masterpiece_of_Gothic_Decor.csv archive\llamalister\
Move-Item .\llamalister\Wildlife_Quilted_Masterpiece_Ducks_Deer_and_Patriotism_Unite.csv archive\llamalister\
Move-Item .\llamalister\__pycache__ archive\llamalister\

# Move cache folders in Core_AUA_System
Move-Item .\Core_AUA_System\__pycache__ archive\Core_AUA_System\
Move-Item .\Core_AUA_System\src\__pycache__ archive\Core_AUA_System\src\
Move-Item .\Core_AUA_System\src\agents\__pycache__ archive\Core_AUA_System\src\agents\
Move-Item .\Core_AUA_System\src\agents\operations\__pycache__ archive\Core_AUA_System\src\agents\operations\
Move-Item .\Core_AUA_System\src\core\__pycache__ archive\Core_AUA_System\src\core\