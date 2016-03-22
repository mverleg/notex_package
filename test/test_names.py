
from pytest import raises
from utils import unique_package_name


def test_name_degeneracy():
	assert unique_package_name('HEY') == 'hey'
	assert unique_package_name('h.1') == 'h_1'
	assert unique_package_name('h_-,.1') == 'h_1'
	assert unique_package_name('q.' * 15 + 'qq') == 'q_' * 15 + 'qq'


def test_name_validity():
	with raises(AssertionError):
		unique_package_name('h@llo')
	with raises(AssertionError):
		unique_package_name('9hello')
	with raises(AssertionError):
		unique_package_name('hello_')
	with raises(AssertionError):
		unique_package_name('hi')
	with raises(AssertionError):
		unique_package_name('q' * 33)


