import pytest

from awx.main.access import (
    RoleAccess,
    UserAccess,
    TeamAccess)
from awx.main.models import Role, Organization


@pytest.mark.django_db
def test_team_access_attach(rando, team, inventory):
    # rando is admin of the team
    team.admin_role.members.add(rando)
    inventory.read_role.members.add(rando)
    # team has read_role for the inventory
    team.member_role.children.add(inventory.read_role)

    access = TeamAccess(rando)
    data = {'id': inventory.admin_role.pk}
    assert not access.can_attach(team, inventory.admin_role, 'member_role.children', data, False)


@pytest.mark.django_db
def test_user_access_attach(rando, inventory):
    inventory.read_role.members.add(rando)
    access = UserAccess(rando)
    data = {'id': inventory.admin_role.pk}
    assert not access.can_attach(rando, inventory.admin_role, 'roles', data, False)


@pytest.mark.django_db
def test_role_access_attach(rando, inventory):
    inventory.read_role.members.add(rando)
    access = RoleAccess(rando)
    assert not access.can_attach(inventory.admin_role, rando, 'members', None)


@pytest.mark.django_db
def test_visible_roles(admin_user, system_auditor, rando, organization, project):
    '''
    system admin & system auditor fixtures needed to create system roles
    '''
    organization.auditor_role.members.add(rando)
    access = RoleAccess(rando)

    assert rando not in organization.admin_role
    assert access.can_read(organization.admin_role)
    assert organization.admin_role in Role.visible_roles(rando)

    assert rando not in project.admin_role
    assert access.can_read(project.admin_role)
    assert project.admin_role in Role.visible_roles(rando)


# Permissions when adding users to org member/admin
@pytest.mark.django_db
def test_org_user_role_attach(user, organization, inventory):
    '''
    Org admins must not be able to add arbitrary users to their
    organization, because that would give them admin permission to that user
    '''
    admin = user('admin')
    nonmember = user('nonmember')
    inventory.admin_role.members.add(nonmember)

    organization.admin_role.members.add(admin)

    role_access = RoleAccess(admin)
    assert not role_access.can_attach(organization.member_role, nonmember, 'members', None)
    assert not role_access.can_attach(organization.admin_role, nonmember, 'members', None)


# Singleton user editing restrictions
@pytest.mark.django_db
def test_org_superuser_role_attach(admin_user, org_admin, organization):
    '''
    Ideally, you would not add superusers to roles (particularly member_role)
    but it has historically been possible
    this checks that the situation does not grant unexpected permissions
    '''
    organization.member_role.members.add(admin_user)

    role_access = RoleAccess(org_admin)
    assert not role_access.can_attach(organization.member_role, admin_user, 'members', None)
    assert not role_access.can_attach(organization.admin_role, admin_user, 'members', None)
    user_access = UserAccess(org_admin)
    assert not user_access.can_change(admin_user, {'last_name': 'Witzel'})


# Sanity check user editing permissions combined with new org roles
@pytest.mark.django_db
def test_org_object_role_not_sufficient(user, organization):
    member = user('amember')
    obj_admin = user('icontrolallworkflows')

    organization.member_role.members.add(member)
    organization.workflow_admin_role.members.add(obj_admin)

    user_access = UserAccess(obj_admin)
    assert not user_access.can_change(member, {'last_name': 'Witzel'})


# Org admin user editing permission ANY to ALL change
@pytest.mark.django_db
def test_need_all_orgs_to_admin_user(user):
    '''
    Old behavior - org admin to ANY organization that a user is member of
        grants permission to admin that user
    New behavior enforced here - org admin to ALL organizations that a
        user is member of grants permission to admin that user
    '''
    org1 = Organization.objects.create(name='org1')
    org2 = Organization.objects.create(name='org2')

    org1_admin = user('org1-admin')
    org1.admin_role.members.add(org1_admin)

    org12_member = user('org12-member')
    org1.member_role.members.add(org12_member)
    org2.member_role.members.add(org12_member)

    user_access = UserAccess(org1_admin)
    assert not user_access.can_change(org12_member, {'last_name': 'Witzel'})

    role_access = RoleAccess(org1_admin)
    assert not role_access.can_attach(org1.admin_role, org12_member, 'members', None)
    assert not role_access.can_attach(org1.member_role, org12_member, 'members', None)

    org2.admin_role.members.add(org1_admin)
    assert role_access.can_attach(org1.admin_role, org12_member, 'members', None)
    assert role_access.can_attach(org1.member_role, org12_member, 'members', None)


# Orphaned user can be added to member role, only in special cases
@pytest.mark.django_db
def test_orphaned_user_allowed(org_admin, rando, organization):
    '''
    We still allow adoption of orphaned* users by assigning them to
    organization member role, but only in the situation where the
    org admin already posesses indirect access to all of the user's roles
    *orphaned means user is not a member of any organization
    '''
    role_access = RoleAccess(org_admin)
    assert role_access.can_attach(organization.member_role, rando, 'members', None)
    # Cannot edit the user directly without adding to org first
    user_access = UserAccess(org_admin)
    assert not user_access.can_change(rando, {'last_name': 'Witzel'})
