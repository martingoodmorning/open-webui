<script lang="ts">
	export let className = 'size-8';
	export let src = '/static/favicon.png';
</script>

<img
	aria-hidden="true"
	src={src === ''
		? '/static/favicon.png'
		: src.startsWith('http://') ||
			  src.startsWith('https://') ||
			  src.startsWith('https://www.gravatar.com/avatar/') ||
			  src.startsWith('data:') ||
			  src.startsWith('/')
			? src
			: '/user.png'}
	class=" {className} object-cover rounded-full"
	alt="profile"
	draggable="false"
/>
