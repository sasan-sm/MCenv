# SPDX-License-Identifier: GPL-3.0-or-later
"""Delegate removal to Blender, never delete installation files ourselves."""
from pathlib import Path
import bpy

MODULE = __package__


def uninstall_target(context, module=MODULE):
    parts = module.split('.')
    root = Path(__file__).resolve().parent
    if len(parts) == 3 and parts[0] == 'bl_ext':
        for index, repo in enumerate(context.preferences.extensions.repos):
            if repo.module == parts[1] and root == (Path(repo.directory)/parts[2]).resolve():
                if getattr(repo,'source','USER') == 'SYSTEM':
                    return None
                return ('extensions.package_uninstall', {'repo_index': index, 'pkg_id': parts[2]})
        return None
    # Only installed user add-ons can be removed. A developer source checkout is never a removal target.
    user_scripts = bpy.utils.user_resource('SCRIPTS')
    if user_scripts and root.is_relative_to((Path(user_scripts)/'addons').resolve()):
        return ('preferences.addon_remove', {'module': module})
    return None


class MCENV_OT_uninstall(bpy.types.Operator):
    bl_idname = 'mcenv.uninstall'
    bl_label = 'Uninstall MCenv'
    bl_description = 'Confirm and uninstall MCenv using Blender\'s package manager; save your .blend first'

    def draw(self, context):
        col = self.layout.column(align=True)
        col.label(text='Disable and uninstall MCenv?', icon='ERROR')
        col.label(text='Save your .blend before continuing.')
        col.label(text='Scene objects and .blend files will not be deleted.')
        col.label(text='Procedural animation will stop until MCenv is reinstalled.')

    def invoke(self, context, event):
        if not uninstall_target(context):
            self.report({'WARNING'}, 'Only an installed user add-on can be uninstalled; development/system files are protected')
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=430, confirm_text='Uninstall MCenv')

    def execute(self, context):
        target = uninstall_target(context)
        if not target:
            self.report({'ERROR'}, 'MCenv is not installed in a removable user add-on location')
            return {'CANCELLED'}
        operator, kwargs = target
        window, area = context.window, context.area
        # Return from our operator before Blender unregisters this very class.
        def remove_later():
            try:
                group, name = operator.split('.')
                op = getattr(getattr(bpy.ops,group),name)
                if window and area:
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    with bpy.context.temp_override(window=window, area=area, region=region):
                        op('EXEC_DEFAULT', **kwargs)
                else:
                    op('EXEC_DEFAULT', **kwargs)
                if bpy.context.preferences.use_preferences_save:
                    bpy.ops.wm.save_userpref()
            except (RuntimeError,ReferenceError,TypeError) as exc:
                print('MCenv uninstall failed:', exc)
                def error_menu(self, _context):
                    self.layout.label(text='Uninstall failed. Use Blender Preferences to remove MCenv.', icon='ERROR')
                if bpy.context.window:
                    bpy.context.window_manager.popup_menu(error_menu,title='MCenv')
            return None
        bpy.app.timers.register(remove_later, first_interval=.2)
        return {'FINISHED'}


class MCENV_Preferences(bpy.types.AddonPreferences):
    bl_idname = MODULE

    def draw(self, context):
        self.layout.label(text='MCenv 0.6.0 · World Properties > MCenv')
        self.layout.label(text='Time and Rotation: right-click > Add to Quick Favorites.')
        self.layout.label(text='Quick Favorites are editor-specific in Blender.', icon='INFO')
        row = self.layout.row()
        row.operator_context = 'INVOKE_DEFAULT'
        row.operator('mcenv.uninstall', text='Uninstall MCenv', icon='TRASH')
        self.layout.label(text='Removes the installed package, not your scene or saved .blend.')


CLASSES = (MCENV_OT_uninstall, MCENV_Preferences)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
