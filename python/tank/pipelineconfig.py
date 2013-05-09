"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

Encapsulates the pipeline configuration and helps navigate and resolve paths
across storages, configurations etc.
"""
import os
import sys
import glob

from tank_vendor import yaml

from .errors import TankError
from .deploy import util
from .platform import constants
from .platform.environment import Environment
from .util import shotgun
from .util import login
from . import template_includes

class PipelineConfiguration(object):
    """
    Represents a pipeline configuration in Tank.
    Use the factory methods above to construct this object, do not 
    create directly via constructor.
    """
    
    def __init__(self, pipeline_configuration_path):
        """
        Constructor. Do not call this directly, use the factory methods
        at the bottom of this file.
        """
        self._pc_root = pipeline_configuration_path
        
        # validate that the current code version matches or is compatible with
        # the code that is locally stored in this config!!!!
        our_version = self.__get_core_version()
        if our_version is not None:
            # we have an API installed locally
            current_api = get_core_api_version_based_on_current_code()
        
            if util.is_version_older(current_api, our_version):
                # currently running API is too old!
                current_api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                raise TankError("You are currently running a Tank API located in '%s'. "
                                "The current Configuration '%s' has separately installed "
                                "version of the API (%s) which is more recent than the currently "
                                "running version (%s). In order to use this pipeline configuration, "
                                "add %s to your PYTHONPATH and try again." % (current_api_path, 
                                                                              self.get_path(), 
                                                                              our_version, 
                                                                              current_api, 
                                                                              self.get_python_location()))
        
        
        self._roots = self.__load_roots_meatadata()
        self.__load_config_metadata()
        self._pc_registered_location = get_pc_registered_location(self._pc_root)
        
                
    def __repr__(self):
        return "<Tank Configuration %s>" % self._pc_root
                
    ########################################################################################
    # helpers

    def __get_core_version(self):
        """
        Returns the version string for the core api associated with this config,
        none if it does not exist.
        """
        info_yml_path = os.path.join(self._pc_root, "install", "core", "info.yml")
        
        if os.path.exists(info_yml_path):
            try:
                info_fh = open(info_yml_path, "r")
                try:
                    data = yaml.load(info_fh)
                finally:
                    info_fh.close()
                data = data.get("version")
            except:
                data = None
        else:
            data = None

        return data
    
    def __load_config_metadata(self):
        """
        Loads the config metadata file
        """
        # now read in the pipeline_configuration.yml file
        cfg_yml = os.path.join(self._pc_root, "config", "core", "pipeline_configuration.yml")
        fh = open(cfg_yml, "rt")
        try:
            data = yaml.load(fh)
        except Exception, e:
            raise TankError("Looks like a config file is corrupt. Please contact "
                            "support! File: '%s' Error: %s" % (cfg_yml, e))
        finally:
            fh.close()
        
        self._project_name = data.get("project_name")
        if self._project_name is None:
            raise TankError("Project name not defined in config metadata for %s! "
                            "Please contact support." % self) 
        

    
    def __load_roots_meatadata(self):
        """
        Loads and validates the roots metadata file
        """
        # now read in the roots.yml file
        # this will contain something like
        # {'primary': {'mac_path': '/studio', 'windows_path': None, 'linux_path': '/studio'}}
        roots_yml = os.path.join(self._pc_root, "config", "core", "roots.yml")  
                 
        fh = open(roots_yml, "rt")
        try:
            data = yaml.load(fh)
        except Exception, e:
            raise TankError("Looks like the roots file is corrupt. Please contact "
                            "support! File: '%s' Error: %s" % (roots_yml, e))
        finally:
            fh.close()
        
        # sanity check that there is a primary root
        if constants.PRIMARY_STORAGE_NAME not in data:
            raise TankError("Could not find a primary storage in roots file for %s!" % self)        
        
        # make sure that all paths are correctly ended without a path separator
        for s in data:
            if data[s]["mac_path"] and data[s]["mac_path"].endswith("/"):
                data[s]["mac_path"] = data[s]["mac_path"][:-1]
            if data[s]["linux_path"] and data[s]["linux_path"].endswith("/"):
                data[s]["linux_path"] = data[s]["linux_path"][:-1]
            if data[s]["windows_path"] and data[s]["windows_path"].endswith("\\"):
                data[s]["windows_path"] = data[s]["windows_path"][:-1]
                
        return data
    
    ########################################################################################
    # data roots access
        
    def get_path(self):
        """
        Returns the master root for this pipeline configuration
        """
        return self._pc_root
        
    def get_registered_location_path(self):
        """
        Returns the path that has been registered for this pipeline configuration 
        for the current OS.
        This is the path that has been defined in shotgun. It is also the path that is being
        used in the inverse pointer files that exist in each storage.
        
        This is useful when drive letter mappings or symlinks are being used - in these
        cases get_path() may not return the same value as get_registered_location_path().
        
        This may return None if no path has been registered for the current os.
        """
        return self._pc_registered_location
        
    def get_data_roots(self):
        """
        Returns a dictionary of all the data roots available for this PC,
        keyed by their storage name. Only returns paths for current platform.
        
        Returns for example:
        
        {"primary": "/studio/my_project", "textures": "/textures/my_project"}
        
        """
        platform_lookup = {"linux2": "linux_path", "win32": "windows_path", "darwin": "mac_path" }
                
        # now pick current os and append project root
        proj_roots = {}
        for r in self._roots:            
            current_os_root = self._roots[r][ platform_lookup[sys.platform] ]
            if current_os_root is None:
                proj_roots[r] = None
            else:
                
                # Note, these paths may have been written from a different platform
                # so the slash direction may not be uniform.  To accomodate this
                # we convert _all_ slashes to the current os.path.sep here
                current_os_root = current_os_root.replace("\\", os.path.sep).replace("/", os.path.sep)
                proj_roots[r] = os.path.join(current_os_root, self._project_name)
        
        return proj_roots
        
    
    def get_primary_data_root(self):
        """
        Returns the path to the primary data root for the current platform
        """
        return self.get_data_roots().get(constants.PRIMARY_STORAGE_NAME)
            
            
    def get_path_cache_location(self):
        """
        Returns the path to the path cache file.
        """
        return os.path.join(self.get_primary_data_root(), "tank", "cache", constants.CACHE_DB_FILENAME)
            
            
    ########################################################################################
    # apps and engines
                        
    def get_python_location(self):
        """
        returns the python root for this install.
        """
        return os.path.join(self.get_install_root(), "core", "python")

    def get_install_root(self):
        """
        Returns the install location, the location where tank caches engines and apps.
        This location is local to the install, so if you run localized core, it will
        be in your PC, if you run studio location core, it will be a shared cache.
        
        If you are a developer and are symlinking the core, this may not work.
        In that case set an environment env TANK_INSTALL_LOCATION and point
        that at the install location.
        """
            
        # locate the studio install root as a location local to this file
        install_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "..", ".."))
        
        if not os.path.exists(install_path):
            if "TANK_INSTALL_LOCATION" in os.environ:
                install_path = os.environ["TANK_INSTALL_LOCATION"]
            else:
                raise TankError("Cannot resolve the install location from the location of the Tank Code! "
                                "This can happen if you try to move or symlink the Tank API. "
                                "Please contact support." )
        return install_path


    def get_apps_location(self):
        """
        Returns the location where apps are stored
        """
        return os.path.join(self.get_install_root(), "apps")        
            
    def get_engines_location(self):
        """
        Returns the location where apps are stored
        """
        return os.path.join(self.get_install_root(), "engines")
            
    def get_frameworks_location(self):
        """
        Returns the location where apps are stored
        """
        return os.path.join(self.get_install_root(), "frameworks")
            
    ########################################################################################
    # cache

    def get_cache_location(self):
        """
        Returns the pipeline config -centric cache location
        """
        return os.path.join(self._pc_root, "cache")

        
    ########################################################################################
    # configuration
            
    def get_core_hooks_location(self):
        """
        Returns the path to the core hooks location
        """
        return os.path.join(self._pc_root, "config", "core", "hooks")
    
    def get_schema_config_location(self):
        """
        returns the location of the schema
        """
        return os.path.join(self._pc_root, "config", "core", "schema")

    def get_config_location(self):
        """
        returns the config folder for the project
        """
        return os.path.join(self._pc_root, "config")

    def get_hooks_location(self):
        """
        returns the hooks folder for the project
        """
        return os.path.join(self._pc_root, "config", "hooks")
    
    def get_environments(self):
        """
        Returns a list with all the environments in this configuration.
        """
        env_root = os.path.join(self._pc_root, "config", "env")           
        env_names = []
        for f in glob.glob(os.path.join(env_root, "*.yml")):
            file_name = os.path.basename(f)
            (name, _) = os.path.splitext(file_name)
            env_names.append(name)
        return env_names
    
    def get_environment(self, env_name, context=None):
        """
        Returns an environment object given an environment name.
        You can use the get_environments() method to get a list of 
        all the environment names.
        """
        env_file = os.path.join(self._pc_root, "config", "env", "%s.yml" % env_name)    
        if not os.path.exists(env_file):     
            raise TankError("Cannot load environment '%s': Environment configuration "
                            "file '%s' does not exist!" % (env_name, env_file))
                
        return Environment(env_file, self, context)
        
    def get_templates_config(self):
        """
        Returns the templates configuration as an object
        """
        templates_file = os.path.join(self._pc_root, "config", "core", constants.CONTENT_TEMPLATES_FILE)
        
        if os.path.exists(templates_file):
            config_file = open(templates_file, "r")
            try:
                data = yaml.load(config_file) or {}
            finally:
                config_file.close()
        else:
            data = {}
    
        # and process include files
        data = template_includes.process_includes(templates_file, data)
    
        return data


class StorageConfigurationMapping(object):
    """
    Handles operation on the mapping from a data root to a pipeline config
    """
    
    def __init__(self, data_root):
        self._root = data_root
        self._config_file = os.path.join(self._root, "tank", "config", constants.CONFIG_BACK_MAPPING_FILE)
        
    def add_pipeline_configuration(self, mac_path, win_path, linux_path):
        """
        Add pipeline configuration mapping to a storage
        """
        data = []
        
        if os.path.exists(self._config_file):
            # we have a config already - so read it in
            fh = open(self._config_file, "rt")
            try:
                data = yaml.load(fh)
            except Exception, e:
                raise TankError("Looks like the config lookup file is corrupt. Please contact "
                                "support! File: '%s' Error: %s" % (self._config_file, e))
            finally:
                fh.close()
        
        # now add our new mapping to this data structure
        new_item = {"darwin": mac_path, "win32": win_path, "linux2": linux_path}
        if new_item not in data:
            data.append(new_item)
        
        # and write the file
        try:
            fh = open(self._config_file, "wt")
            yaml.dump(data, fh)
            fh.close()
        except Exception, exp:
            raise TankError("Could not write to roots file %s. "
                            "Error reported: %s" % (self._config_file, exp))
        

    def get_pipeline_configs(self):
        """
        Returns a list of current os paths to pipeline configs
        """
        data = []
        
        if os.path.exists(self._config_file):
            # we have a config already - so read it in
            fh = open(self._config_file, "rt")
            try:
                data = yaml.load(fh)
            except Exception, e:
                raise TankError("Looks like the config lookup file %s is corrupt. Please contact "
                                "support! File: '%s' Error: %s" % (self._config_file, e))
            finally:
                fh.close()
        
        current_os_paths = [ x.get(sys.platform) for x in data ]
        return current_os_paths
        
    

def from_entity(entity_type, entity_id):
    """
    Factory method that constructs a PC given a shotgun object
    """
    
    platform_lookup = {"linux2": "linux_path", "win32": "windows_path", "darwin": "mac_path" }
    
    sg = shotgun.create_sg_connection()
    
    e = sg.find_one(entity_type, [["id", "is", entity_id]], ["project"])
    
    if e is None:
        raise TankError("Cannot resolve a pipeline configuration object from %s %s - this object "
                        "does not exist in Shotgun!" % (entity_type, entity_id))
    
    if entity_type == "Project":
        proj = {"type": "Project", "id": entity_id}

    else:
        if e.get("project") is None:
            raise TankError("Cannot resolve a pipeline configuration object from %s %s - this object "
                            "is not linked to a project!" % (entity_type, entity_id))    
        proj = e.get("project")
    
    pipe_configs = sg.find(constants.PIPELINE_CONFIGURATION_ENTITY, 
                           [["project", "is", proj]], 
                           ["windows_path", "mac_path", "linux_path", "code"])
    
    if len(pipe_configs) == 0:
        raise TankError("Cannot resolve a pipeline configuration object from %s with id %s - looks "
                        "like its associated Shotgun Project '%s' has not yet been set up with "
                        "Tank!" % (entity_type, entity_id, proj.get("name")))
    
    #############################################################################################
    # ok now we have all the PCs in Shotgun for this project.
    # apply the following logic:
    #
    # if this method was called from a generic tank command, just find the primary PC 
    # and use that.
    #
    # if this was called from a specific tank command, use that. 
    
    if "TANK_CURRENT_PC" not in os.environ:
        # we are running the generic tank command, the code that we are running
        # is not connected to any particular PC.
        # in this case, find the primary pipeline config and use that
        primary_pc = None
        for pc in pipe_configs:
            if pc.get("code") == constants.PRIMARY_PIPELINE_CONFIG_NAME:
                primary_pc = pc
                break
        if primary_pc is None:
            raise TankError("The Shotgun Project '%s' does not have a default Pipeline "
                            "Configuration! This is required by Tank. It needs to be named '%s'. "
                            "Please double check by opening to the Pipeline configuration Page in "
                            "Shotgun for the given project." % (proj.get("name"), constants.PRIMARY_PIPELINE_CONFIG_NAME))
        
        # check that there is a path for our platform
        current_os_path = primary_pc.get(platform_lookup[sys.platform])
        if current_os_path is None:
            raise TankError("The Shotgun Project '%s' has a Primary pipeline configuration but "
                            "it has not been configured to work with the current "
                            "operating system." % proj.get("name"))

        # ok there is a path - now check that the path exists!
        if not os.path.exists(current_os_path):
            raise TankError("The Shotgun Project '%s' has a Primary pipeline configuration registered "
                            "to be located in '%s', however this path does cannot be "
                            "found!" % (proj.get("name"), current_os_path))
        
        # looks good, we got a primary pipeline config that exists
        return PipelineConfiguration(current_os_path)
        
        
        
        
    else:
        # we are running the tank command from a specific PC.
        # in this case we need to check that the entity actually belongs to the project
        curr_pc_path = os.environ["TANK_CURRENT_PC"]
        
        # do a bit of cleanup - windows paths can end with a space
        if curr_pc_path.endswith(" "):
            curr_pc_path = curr_pc_path[:-1]   
        # windows tends to end with a backslash
        if curr_pc_path.endswith("\\"):
            curr_pc_path = curr_pc_path[:-1]   
            
        # the path stored in the TANK_CURRENT_PC env var may be a symlink etc.
        # now we need to find which PC entity this corresponds to in Shotgun.
        # Once found, we can double check that the current Entity is actually
        # associated with the projec that the PC is associated with.
        
        pc_registered_path = get_pc_registered_location(curr_pc_path)

        if pc_registered_path is None:
            raise TankError("Error starting tank from the tank command located in '%s' - "
                            "it looks like this pipeline configuration and tank command "
                            "has not been configured for the current operating system." % curr_pc_path)
        
        # now that we have the proper pc path, we can find which PC entity this is
        current_os_path = None
        for pc in pipe_configs:
            curr_path = pc.get(platform_lookup[sys.platform])
            if curr_path == pc_registered_path:
                current_os_path = curr_path
                break
        
        if current_os_path is None:
            raise TankError("Error launching tank for %s with id %s (Belonging to the project '%s') "
                            "from the tank command located in '%s'. This tank command is not " 
                            "associated with that project. For a list of which tank commands can be " 
                            "used with this project, go to the Pipeline Configurations page in "
                            "Shotgun for the project." % (entity_type, entity_id, proj.get("name"), curr_pc_path))
        
        # ok we got a pipeline config matching the tank command from which we launched.
        # because we found the PC in the list of PCs for this project, we know that it must be valid!
        return PipelineConfiguration(current_os_path)
         
        
    

def from_path(path):
    """
    Factory method that constructs a PC object from a path:
    - data paths are being traversed and resolved
    - if the path is a direct path to a PC root that's fine too
    """

    if not isinstance(path, basestring):
        raise TankError("Cannot create a Tank Configuration from path '%s' - "
                        "path must be a string!" % path)        

    path = os.path.abspath(path)
    
    # make sure folder exists on disk
    if not os.path.exists(path):        
        # there are cases when a PC is being created from a _file_ which does not yet 
        # exist on disk. To try to be reasonable with this case, try this check on the
        # parent folder of the path as a last resort.
        parent_path = os.path.dirname(path)
        if os.path.exists(parent_path):
            path = parent_path
        else:
            raise TankError("Cannot create a Tank Configuration from path '%s' - the path does "
                            "not exist on disk!" % path)
    
    # first see if this path is a pipeline configuration
    pc_config = os.path.join(path, "config", "core", "pipeline_configuration.yml")
    if os.path.exists(pc_config):
        # done deal!
        return PipelineConfiguration(path)
    
    # if not, walk up until a tank folder is found, 
    # find tank config directory
    cur_path = path
    config_path = None
    while True:
        config_path = os.path.join(cur_path, "tank", "config", constants.CONFIG_BACK_MAPPING_FILE)
        # need to test for something in project vs studio config
        if os.path.exists(config_path):
            break
        parent_path = os.path.dirname(cur_path)
        if parent_path == cur_path:
            # Topped out without finding config
            raise TankError("Cannot create a Tank Configuration from path '%s' - the path does "
                            "not belong to a Tank Project!" % path)
        cur_path = parent_path
    
    # all right - now read the config and find the right pipeline configuration
    try:
        fh = open(config_path, "r")
        try:
            data = yaml.load(fh)
        finally:
            fh.close()
    except Exception, e:        
        raise TankError("Looks like a config file is corrupt. Please contact "
                        "support! File: '%s' Error: %s" % (config_path, e))
        
    # get all the registered pcs for the current platform
    current_os_pcs = [ x.get(sys.platform) for x in data if x is not None]

    # find PCs that exist on disk
    existing_matching_pcs = []
    for pc in current_os_pcs:
        if os.path.exists(pc):
            existing_matching_pcs.append(pc)

    # first see if we came from a specific PC/tank command. In that case, we should use that
    if "TANK_CURRENT_PC" in os.environ:
        curr_pc_path = os.environ["TANK_CURRENT_PC"]
        
        # windows paths can end with a space
        if curr_pc_path.endswith(" "):
            curr_pc_path = curr_pc_path[:-1]   

        # windows tends to end with a backslash
        if curr_pc_path.endswith("\\"):
            curr_pc_path = curr_pc_path[:-1]   

        if curr_pc_path in existing_matching_pcs:
            # ok found our PC
            return PipelineConfiguration(curr_pc_path)
        
        else:
            # weird. environment variable path not in list of choices.
            # means we started tank from a PC which is not associated with this project.
            raise TankError("Cannot create a Tank Configuration for path '%s' by running "
                            "the Tank command located in '%s' - that configuration is not associated "
                            "with the data in %s! Make sure that you launch tank from a "
                            "pipeline configuration that is associated with the folder. You "
                            "can easily see which configurations are valid by going to the "
                            "Shotgun project that the path '%s' belongs to, and "
                            "navigating to the 'pipeline configurations' page." % (path, curr_pc_path, path, path))
        
    # if we are here, we launched tank from a generic studio command.

    # if there is a single entry things are easy....
    if len(existing_matching_pcs) == 1:
        return PipelineConfiguration(existing_matching_pcs[0])
    
    else:
        # ok so we launched from the studio location and there is ambiguity. 
        # query shotgun to resolve this.
        sg = shotgun.create_sg_connection()
        platform_lookup = {"linux2": "linux_path", "win32": "windows_path", "darwin": "mac_path" }
        # get all PCs which has our path
        filters = [platform_lookup[sys.platform], "in"]
        filters.extend(existing_matching_pcs)
        pipe_configs = sg.find(constants.PIPELINE_CONFIGURATION_ENTITY, 
                               [filters], 
                               ["code", "users", "windows_path", "mac_path", "linux_path"])

        # get the current user (none if not found)
        current_user = login.get_shotgun_user(sg)

        # find relevant PCs
        matching_pcs = []
        for p in pipe_configs:
            if p.get("users") is None or len(p.get("users")) == 0:
                # an open PC
                matching_pcs.append(p)
            elif current_user is not None:
                # we have a current user
                # we have users associated with PC
                user_ids = [ x.get("id") for x in p.get("users") ]
                if current_user.get("id") in user_ids:
                    matching_pcs.append(p)
        
        if len(matching_pcs) == 0:
            raise TankError("Cannot resolve a pipeline configuration object from path '%s' - "
                            "No valid Configurations found in Shotgun! Navigate to Shotgun, "
                            "select the project that the path '%s' belongs to and choose "
                            "the pipeline configurations page. Check that there is a configuration " 
                            "which you can access. Alternatively, start tank specifically from "
                            "the pipeline configuration you would like to use." % (path, path))
        
        elif len(matching_pcs) > 1:
            pc_names = ", ".join([x.get("code") for x in matching_pcs])
            tk_cmds = ", ".join([x.get(platform_lookup[sys.platform]) for x in matching_pcs])
            raise TankError("Cannot resolve a pipeline configuration object from path '%s' - "
                            "The following configurations are all matching: %s. Tank does not "
                            "know which one to pick. Try executing the tank command directly "
                            "from one of the locations: %s" % (path, pc_names, tk_cmds)) 

        else:
            pc_path = matching_pcs[0][ platform_lookup[sys.platform] ]
            return PipelineConfiguration(pc_path)
            

    


        
def get_core_api_version_based_on_current_code():
    """
    Returns the version number string for the core API, based on the code that is currently
    executing.
    """
    # read this from info.yml
    info_yml_path = os.path.abspath(os.path.join( os.path.dirname(__file__), "..", "..", "info.yml"))
    try:
        info_fh = open(info_yml_path, "r")
        try:
            data = yaml.load(info_fh)
        finally:
            info_fh.close()
        data = str(data.get("version", "unknown"))
    except:
        data = "unknown"

    return data

def get_pc_registered_location(pipeline_config_root_path):
    """
    Loads the location metadata file from install_location.yml
    This contains a reflection of the paths given in the pc entity.

    Returns the path that has been registered for this pipeline configuration 
    for the current OS.
    This is the path that has been defined in shotgun. It is also the path that is being
    used in the inverse pointer files that exist in each storage.
    
    This is useful when drive letter mappings or symlinks are being used - in these
    cases get_path() may not return the same value as get_registered_location_path().
    
    This may return None if no path has been registered for the current os.
    """
    # now read in the pipeline_configuration.yml file
    cfg_yml = os.path.join(pipeline_config_root_path, "config", "core", "install_location.yml")
    fh = open(cfg_yml, "rt")
    try:
        data = yaml.load(fh)
    except Exception, e:
        raise TankError("Looks like a config file is corrupt. Please contact "
                        "support! File: '%s' Error: %s" % (cfg_yml, e))
    finally:
        fh.close()
    
    if sys.platform == "linux2":
        return data.get("Linux")
    elif sys.platform == "win32":
        return data.get("Windows")
    elif sys.platform == "darwin":
        return data.get("Darwin")
    else:
        raise TankError("Unsupported platform '%s'" % sys.platform)

