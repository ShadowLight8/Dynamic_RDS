<?php

# $menuEntries is an array of menu entries for this plugin
# text - menu entry text
# type - status/content/output/help (main menu area)
# page - PHP file to display for this menu item
# wrap - 0/1 to hide or display the FPP header, menu, and footer on this page.
#        This does not apply for pages which begin with http:// or https://

# Comment out sub arrays to not display an item under a menu or add your own
# entries to display additional menu items such as the 3 items under the
# help menu in this example template.

$menuEntries = Array(
	Array(
		'text' => 'Dynamic RDS',
		'type' => 'status',
		'page' => 'Dynamic_RDS.php',
		'wrap' => 1
	)
);

##############################################################################
# Display the menu entries for this plugin.
#
# It is expected that two variables are alread set:
# $plugin - contains the name of the current plugin directory/repoName
# $menu - contains the name of the menu section/type
foreach ($menuEntries as $entry)
{
	if ($entry['type'] != $menu)
		continue;

	if (preg_match('/^http.?:\/\//', $entry['page']))
	{
		printf("<li><a href='%s' target='_blank'>%s</a></li>\n",
			$entry['page'], $entry['text']);
	}
	else
	{
		$nopage = '';
		if (isset($entry['wrap']) && ($entry['wrap'] == 0))
			$nopage = '&nopage=1';

		printf("<li><a href='plugin.php?plugin=%s&page=%s%s'><i class='fas fa-radio'></i> %s</a></li>\n",
			$plugin, $entry['page'], $nopage, $entry['text']);
	}
}
?>
