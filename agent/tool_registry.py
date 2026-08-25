from tools.filesystem import analyze_file_relevance, get_folder_size, search_files
from tools.processes import get_network_connections, list_running_processes
from tools.registry import list_installed_apps, query_registry
from tools.system import get_disk_health, get_gpu_driver_info, get_system_diagnostics
from tools.websearch import fetch_page, get_approximate_location, web_search

TOOL_REGISTRY = {
    "get_system_diagnostics": get_system_diagnostics,
    "list_running_processes": list_running_processes,
    "get_network_connections": get_network_connections,
    "get_gpu_driver_info": get_gpu_driver_info,
    "get_disk_health": get_disk_health,
    "query_registry": query_registry,
    "list_installed_apps": list_installed_apps,
    "search_files": search_files,
    "get_folder_size": get_folder_size,
    "analyze_file_relevance": analyze_file_relevance,
    "web_search": web_search,
    "fetch_page": fetch_page,
    "get_approximate_location": get_approximate_location,
}
